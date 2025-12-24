"""
🤖 بوت تمويل القنوات - النسخة النهائية الكاملة
مطور خصيصاً للمدير: 6130994941
مع جميع المميزات المطلوبة + نظام بقاء نشط
"""

# ==================== 📥 استيراد المكتبات ====================
import os
import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from threading import Thread
import requests

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError, UserPrivacyRestrictedError

from sqlalchemy import create_engine, Column, Integer, String, Boolean, BigInteger, DateTime, Text, func, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ==================== ⚙️ الإعدادات ====================
class Config:
    """إعدادات البوت"""
    # 🔑 التوكن الخاص بالبوت
    BOT_TOKEN = "8436742877:AAGhCfnC9hbW7Sa4gMTroYissoljCjda9Ow"
    
    # 👑 المدير الرئيسي
    ADMIN_ID = 6130994941
    
    # 🗄️ قاعدة البيانات
    DATABASE_URL = "sqlite:///bot_database.db"
    
    # ⚙️ إعدادات النظام
    MAINTENANCE_MODE = False
    MAINTENANCE_MESSAGE = "🔧 البوت تحت الصيانة حالياً، الرجاء المحاولة لاحقاً."
    TRANSFER_FEE_PERCENT = 5
    TRANSFER_ENABLED = True
    
    # ⭐ إعدادات النقاط
    POINTS_PER_REFERRAL = 5
    DAILY_GIFT_POINTS = 3
    POINTS_PER_CHANNEL_SUB = 2
    MIN_POINTS_FOR_FUNDING = 25
    POINTS_PER_MEMBER = 25
    
    # ⚡ إعدادات الأداء
    MAX_MEMBERS_PER_REQUEST = 50
    ADD_MEMBERS_DELAY = 1
    PORT = 8080
    
    # 🔄 نظام البقاء نشط
    KEEP_ALIVE_INTERVAL = 300  # كل 5 دقائق

# ==================== 🗄️ قاعدة البيانات ====================
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    points = Column(Integer, default=0)
    referrals = Column(Integer, default=0)
    referred_by = Column(BigInteger, nullable=True)
    is_banned = Column(Boolean, default=False)
    ban_reason = Column(Text, nullable=True)
    is_admin = Column(Boolean, default=False)
    admin_permissions = Column(String(500), default='["all"]')
    last_daily_gift = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class Channel(Base):
    __tablename__ = 'channels'
    id = Column(Integer, primary_key=True)
    channel_id = Column(String(100), nullable=False)
    channel_username = Column(String(100))
    channel_title = Column(String(200))
    is_private = Column(Boolean, default=False)
    is_mandatory = Column(Boolean, default=False)
    required_members = Column(Integer, default=0)
    current_members = Column(Integer, default=0)
    added_by_admin = Column(BigInteger)
    created_at = Column(DateTime, default=datetime.now)

class GroupSource(Base):
    __tablename__ = 'group_sources'
    id = Column(Integer, primary_key=True)
    group_id = Column(String(100), nullable=False)
    group_username = Column(String(100))
    group_title = Column(String(200))
    is_private = Column(Boolean, default=False)
    member_count = Column(Integer, default=0)
    added_by_admin = Column(BigInteger)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

class FundingRequest(Base):
    __tablename__ = 'funding_requests'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    target_channel = Column(String(100), nullable=False)
    target_type = Column(String(20), nullable=False)
    requested_members = Column(Integer, nullable=False)
    points_cost = Column(Integer, nullable=False)
    status = Column(String(20), default='pending')
    approved_by = Column(BigInteger, nullable=True)
    completed_members = Column(Integer, default=0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class PointsTransfer(Base):
    __tablename__ = 'points_transfers'
    id = Column(Integer, primary_key=True)
    from_user_id = Column(BigInteger, nullable=False)
    to_user_id = Column(BigInteger, nullable=False)
    amount = Column(Integer, nullable=False)
    fee_percent = Column(Integer, nullable=False)
    fee_amount = Column(Integer, nullable=False)
    net_amount = Column(Integer, nullable=False)
    transfer_date = Column(DateTime, default=datetime.now)

class SupportContact(Base):
    __tablename__ = 'support_contacts'
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100))
    is_active = Column(Boolean, default=True)
    added_by = Column(BigInteger)
    added_at = Column(DateTime, default=datetime.now)

class SystemSettings(Base):
    __tablename__ = 'system_settings'
    id = Column(Integer, primary_key=True)
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(Text, default='🔧 البوت تحت الصيانة حالياً')
    transfer_enabled = Column(Boolean, default=True)
    transfer_fee_percent = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.now)

class PointsSettings(Base):
    __tablename__ = 'points_settings'
    id = Column(Integer, primary_key=True)
    points_per_member = Column(Integer, default=25)
    points_per_referral = Column(Integer, default=5)
    daily_gift_points = Column(Integer, default=3)
    points_per_channel = Column(Integer, default=2)
    min_points_for_funding = Column(Integer, default=25)
    updated_at = Column(DateTime, default=datetime.now)

# ==================== 🛠️ إدارة قاعدة البيانات ====================
engine = create_engine(Config.DATABASE_URL, echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

def get_db():
    """الحصول على جلسة قاعدة البيانات"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def init_database():
    """تهيئة قاعدة البيانات مع البيانات الأساسية"""
    db = get_db()
    try:
        # إعدادات النظام
        if db.query(SystemSettings).count() == 0:
            settings = SystemSettings()
            db.add(settings)
        
        # إعدادات النقاط
        if db.query(PointsSettings).count() == 0:
            points_settings = PointsSettings()
            db.add(points_settings)
        
        # المدير الرئيسي
        admin_user = db.query(User).filter_by(user_id=Config.ADMIN_ID).first()
        if not admin_user:
            admin_user = User(
                user_id=Config.ADMIN_ID,
                username="admin",
                first_name="👑 المدير الرئيسي",
                is_admin=True,
                admin_permissions='["all"]'
            )
            db.add(admin_user)
        
        db.commit()
        print("✅ تم تهيئة قاعدة البيانات بنجاح")
    except Exception as e:
        print(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        db.rollback()
    finally:
        db.close()

# ==================== 🔄 نظام البقاء نشط ====================
class KeepAlive:
    """نظام للحفاظ على نشاط البوت على السيرفرات المجانية"""
    
    @staticmethod
    def start_keep_alive_server():
        """بدء خادم ويب صغير"""
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return "🤖 البوت يعمل بنجاح | " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        @app.route('/health')
        def health():
            return {"status": "active", "timestamp": datetime.now().isoformat()}
        
        def run():
            app.run(host='0.0.0.0', port=Config.PORT)
        
        Thread(target=run, daemon=True).start()
        print(f"✅ خادم البقاء نشط يعمل على المنفذ {Config.PORT}")
    
    @staticmethod
    async def send_keep_alive_ping(bot):
        """إرسال رسالة ping للبوت نفسه كل 5 دقائق"""
        try:
            # إرسال أمر /start للبوت نفسه
            await bot.send_message(
                chat_id=Config.ADMIN_ID,
                text=f"🔄 ping - {datetime.now().strftime('%H:%M:%S')}"
            )
            print(f"✅ تم إرسال ping في {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            print(f"⚠️ فشل إرسال ping: {e}")
    
    @staticmethod
    def start_scheduler(bot):
        """بدء المجدول لإرسال ping دوري"""
        scheduler = BackgroundScheduler()
        
        async def ping_job():
            await KeepAlive.send_keep_alive_ping(bot)
        
        # جدولة ping كل 5 دقائق
        scheduler.add_job(
            lambda: asyncio.run(ping_job()),
            'interval',
            minutes=5,
            id='keep_alive_ping'
        )
        
        scheduler.start()
        print("✅ تم تشغيل مجدول البقاء نشط (كل 5 دقائق)")

# ==================== 🤖 فئة البوت الرئيسية ====================
class TelegramFundingBot:
    """الفئة الرئيسية للبوت"""
    
    def __init__(self):
        self.config = Config
        self.db = get_db
        self.application = None
        self.keep_alive = KeepAlive()
        
    # ==================== 🔧 دوال المساعدة ====================
    def extract_channel_id(self, link: str) -> Optional[str]:
        """استخراج معرف القناة من الرابط"""
        if link.startswith('@'):
            return link
        elif 't.me/' in link:
            parts = link.split('t.me/')
            if len(parts) > 1:
                channel_part = parts[1].split('/')[0]
                if channel_part.startswith('+'):
                    return channel_part
                else:
                    return '@' + channel_part
        return None
    
    async def check_mandatory_channels(self, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """التحقق من اشتراك المستخدم في القنوات الإجبارية"""
        db = self.db()
        try:
            channels = db.query(Channel).filter_by(is_mandatory=True).all()
            for channel in channels:
                try:
                    member = await context.bot.get_chat_member(channel.channel_id, user_id)
                    if member.status in ['left', 'kicked']:
                        return False
                except:
                    continue
            return True
        finally:
            db.close()
    
    async def check_maintenance(self, update: Update) -> bool:
        """التحقق من وضع الصيانة"""
        db = self.db()
        try:
            settings = db.query(SystemSettings).first()
            if settings and settings.maintenance_mode:
                user = db.query(User).filter_by(user_id=update.effective_user.id).first()
                # استثناء للمشرفين
                if not user or not user.is_admin:
                    await update.message.reply_text(settings.maintenance_message)
                    return True
            return False
        finally:
            db.close()
    
    # ==================== 👤 معالجة المستخدمين ====================
    async def register_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[User]:
        """تسجيل مستخدم جديد"""
        user_id = update.effective_user.id
        db = self.db()
        
        try:
            # التحقق إذا المستخدم مسجل مسبقاً
            user = db.query(User).filter_by(user_id=user_id).first()
            if user:
                return user
            
            # تسجيل مستخدم جديد
            user = User(
                user_id=user_id,
                username=update.effective_user.username or "",
                first_name=update.effective_user.first_name or "",
                last_name=update.effective_user.last_name or "",
                created_at=datetime.now()
            )
            
            # معالجة الإحالة
            if context.args:
                try:
                    referrer_id = int(context.args[0])
                    referrer = db.query(User).filter_by(user_id=referrer_id).first()
                    if referrer and referrer_id != user_id:
                        points_settings = db.query(PointsSettings).first()
                        if points_settings:
                            referrer.points += points_settings.points_per_referral
                            referrer.referrals += 1
                            user.referred_by = referrer_id
                except:
                    pass
            
            db.add(user)
            db.commit()
            return user
            
        except Exception as e:
            print(f"خطأ في تسجيل المستخدم: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    # ==================== 🎯 معالجة الأوامر ====================
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        # التحقق من وضع الصيانة
        if await self.check_maintenance(update):
            return
        
        user_id = update.effective_user.id
        
        # التحقق من الاشتراك الإجباري
        if not await self.check_mandatory_channels(user_id, context):
            await self.show_mandatory_channels_start(update, context)
            return
        
        # تسجيل المستخدم
        user = await self.register_user(update, context)
        if not user:
            await update.message.reply_text("❌ حدث خطأ في التسجيل!")
            return
        
        # التحقق من الحظر
        if user.is_banned:
            await update.message.reply_text(f"🚫 حسابك محظور\nالسبب: {user.ban_reason}")
            return
        
        # عرض القائمة الرئيسية
        await self.show_main_menu(update, context, user)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user: User):
        """عرض القائمة الرئيسية"""
        welcome_text = f"""
👋 أهلاً بك {user.first_name}!

🆔 إيديك: `{user.user_id}`
⭐ نقاطك: {user.points:,}
📊 عدد دعواتك: {user.referrals}

اختر من القائمة:
"""
        
        keyboard = []
        
        # زر لوحة التحكم للمشرفين فقط
        if user.is_admin:
            keyboard.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_panel")])
        
        # الأزرار الأساسية
        keyboard.extend([
            [InlineKeyboardButton("👥 زيادة المشتركين", callback_data="increase_members")],
            [InlineKeyboardButton("⭐ نقاطي", callback_data="my_points")],
            [InlineKeyboardButton("🔄 تحويل النقاط", callback_data="transfer_points")],
            [InlineKeyboardButton("📢 قنوات إجبارية", callback_data="mandatory_channels")],
            [InlineKeyboardButton("📞 تواصل مع الدعم", callback_data="contact_support")],
            [InlineKeyboardButton("🔗 رابط الدعوة", callback_data="invite_link")],
            [InlineKeyboardButton("🎁 الهدية اليومية", callback_data="daily_gift")],
            [InlineKeyboardButton("📋 طلباتي", callback_data="my_requests")]
        ])
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                welcome_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    # ==================== 🔘 معالجة الأزرار ====================
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة ضغطات الأزرار"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id
        
        # التحقق من وضع الصيانة
        if await self.check_maintenance(update):
            return
        
        # توجيه حسب الزر المضغوط
        if data == "admin_panel":
            await self.show_admin_panel(query, context)
        elif data == "increase_members":
            await self.show_increase_members(query, context)
        elif data == "my_points":
            await self.show_my_points(query, context)
        elif data == "transfer_points":
            await self.show_transfer_points(query, context)
        elif data == "mandatory_channels":
            await self.show_mandatory_channels_menu(query, context)
        elif data == "contact_support":
            await self.show_support_contacts(query, context)
        elif data == "invite_link":
            await self.show_invite_link(query, context)
        elif data == "daily_gift":
            await self.give_daily_gift(query, context)
        elif data == "my_requests":
            await self.show_my_requests(query, context)
        elif data == "check_subscription":
            await self.handle_check_subscription(query, context)
        elif data == "back_to_main":
            await self.back_to_main_menu(query, context)
        elif data.startswith("funding_type_"):
            await self.handle_funding_type(query, context, data)
        elif data == "start_transfer":
            await self.start_transfer_process(query, context)
        elif data == "transfer_history":
            await self.show_transfer_history(query, context)
    
    async def handle_check_subscription(self, query, context):
        """معالجة التحقق من الاشتراك"""
        if await self.check_mandatory_channels(query.from_user.id, context):
            db = self.db()
            try:
                user = db.query(User).filter_by(user_id=query.from_user.id).first()
                if user:
                    await self.show_main_menu(update, context, user)
            finally:
                db.close()
        else:
            await query.answer("❌ لم تشترك في كل القنوات بعد!", show_alert=True)
    
    async def back_to_main_menu(self, query, context):
        """العودة للقائمة الرئيسية"""
        db = self.db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if user:
                await self.show_main_menu(update, context, user)
        finally:
            db.close()
    
    async def handle_funding_type(self, query, context, data):
        """معالجة نوع التمويل"""
        funding_type = data.split("_")[2]
        context.user_data['funding_type'] = funding_type
        
        db = self.db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else self.config.POINTS_PER_MEMBER
            
            await query.edit_message_text(
                f"📝 ارسل عدد الأعضاء المطلوب ({funding_type}):\n\n"
                f"💎 سعر العضو الواحد: {points_per_member} نقطة\n"
                f"💰 احسب التكلفة: (العدد × {points_per_member})"
            )
        finally:
            db.close()
    
    async def start_transfer_process(self, query, context):
        """بدء عملية تحويل النقاط"""
        await query.edit_message_text(
            "🔄 تحويل النقاط\n\n"
            "ارسل رسالة بالشكل التالي:\n"
            "`تحويل [المبلغ] [إيدي المستخدم]`\n\n"
            "مثال: `تحويل 100 123456789`\n\n"
            "💡 عمولة التحويل: 5% (قابلة للتغيير من لوحة التحكم)"
        )
    
    # ==================== 📱 واجهات المستخدم ====================
    async def show_increase_members(self, query, context):
        """عرض واجهة زيادة الأعضاء"""
        db = self.db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            min_points = points_settings.min_points_for_funding if points_settings else self.config.MIN_POINTS_FOR_FUNDING
            
            if user.points < min_points:
                await query.answer(f"❌ تحتاج على الأقل {min_points} نقطة لطلب التمويل!", show_alert=True)
                return
            
            keyboard = [
                [InlineKeyboardButton("📢 قناة عامة", callback_data="funding_type_channel")],
                [InlineKeyboardButton("👥 مجموعة", callback_data="funding_type_group")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                "اختر نوع القناة/المجموعة التي تريد زيادة أعضائها:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_my_points(self, query, context):
        """عرض نقاط المستخدم"""
        db = self.db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            
            points_text = f"""
⭐ نقاطك الحالية: {user.points:,}

طرق زيادة النقاط:
1. 🔗 دعوة أصدقاء: {points_settings.points_per_referral if points_settings else 5} نقاط لكل صديق
2. 📢 الاشتراك في القنوات: {points_settings.points_per_channel if points_settings else 2} نقاط لكل قناة
3. 🎁 الهدية اليومية: {points_settings.daily_gift_points if points_settings else 3} نقاط يومياً
4. 💰 شراء النقاط: تواصل مع الدعم

أقل حد للتمويل: {points_settings.min_points_for_funding if points_settings else 25} نقطة
"""
            
            keyboard = [
                [InlineKeyboardButton("🔄 تحويل النقاط", callback_data="transfer_points")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                points_text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_transfer_points(self, query, context):
        """عرض واجهة تحويل النقاط"""
        db = self.db()
        try:
            settings = db.query(SystemSettings).first()
            if not settings or not settings.transfer_enabled:
                await query.answer("❌ خدمة تحويل النقاط معطلة حالياً!", show_alert=True)
                return
            
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            keyboard = [
                [InlineKeyboardButton("🚀 بدء التحويل", callback_data="start_transfer")],
                [InlineKeyboardButton("📋 سجل التحويلات", callback_data="transfer_history")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                f"🔄 تحويل النقاط\n\n"
                f"⭐ نقاطك الحالية: {user.points:,}\n"
                f"💸 عمولة التحويل: {settings.transfer_fee_percent}%\n"
                f"📤 أقصى مبلغ للتحويل: لا يوجد حد\n\n"
                f"اختر الإجراء:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_mandatory_channels_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض قنوات الاشتراك الإجباري عند البدء"""
        db = self.db()
        try:
            channels = db.query(Channel).filter_by(is_mandatory=True).all()
            
            if not channels:
                # لا توجد قنوات إجبارية
                return
            
            keyboard = []
            for channel in channels:
                if channel.channel_username:
                    username = channel.channel_username.replace('@', '')
                    keyboard.append([
                        InlineKeyboardButton(
                            f"اشترك في {channel.channel_title or username}",
                            url=f"https://t.me/{username}"
                        )
                    ])
            
            keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")])
            
            await update.message.reply_text(
                "⚠️ يجب الاشتراك في القنوات التالية أولاً:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_mandatory_channels_menu(self, query, context):
        """عرض قنوات الاشتراك الإجباري في القائمة"""
        db = self.db()
        try:
            channels = db.query(Channel).filter_by(is_mandatory=True).all()
            
            if not channels:
                text = "✅ لا توجد قنوات إجبارية حالياً."
            else:
                text = "📢 قنوات الاشتراك الإجباري:\n\n"
                for i, channel in enumerate(channels, 1):
                    is_subscribed = await self.check_mandatory_channels(query.from_user.id, context)
                    status = "✅ مشترك" if is_subscribed else "❌ غير مشترك"
                    username = channel.channel_username or channel.channel_id
                    text += f"{i}. {channel.channel_title or username}\n{status}\n\n"
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_support_contacts(self, query, context):
        """عرض جهات اتصال الدعم الفني"""
        db = self.db()
        try:
            support_contacts = db.query(SupportContact).filter_by(is_active=True).all()
            
            if not support_contacts:
                text = "📞 لا يوجد ممثلين للدعم حالياً."
            else:
                text = "📞 قائمة ممثلي الدعم الفني:\n\n"
                for contact in support_contacts:
                    text += f"• @{contact.username}\n"
                text += "\nراسل أي ممثل للشحن أو الاستفسار."
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_invite_link(self, query, context):
        """عرض رابط الدعوة"""
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start={query.from_user.id}"
        
        db = self.db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_referral = points_settings.points_per_referral if points_settings else self.config.POINTS_PER_REFERRAL
            
            text = f"""
🔗 رابط دعوتك الخاص:

`{invite_link}`

📊 لكل صديق تدعوه: {points_per_referral} نقاط
⭐ النقاط تخصم فور اشتراك صديقك
"""
            
            keyboard = [
                [InlineKeyboardButton("🔗 نسخ الرابط", callback_data="copy_link")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        finally:
            db.close()
    
    async def show_my_requests(self, query, context):
        """عرض طلبات المستخدم"""
        db = self.db()
        try:
            requests = db.query(FundingRequest).filter_by(user_id=query.from_user.id).order_by(FundingRequest.created_at.desc()).limit(5).all()
            
            if not requests:
                text = "📋 لا توجد طلبات سابقة."
            else:
                text = "📋 آخر 5 طلبات:\n\n"
                for req in requests:
                    status_emoji = {
                        'pending': '⏳',
                        'approved': '✅',
                        'completed': '🎉',
                        'rejected': '❌'
                    }.get(req.status, '📝')
                    
                    text += (
                        f"طلب #{req.id}\n"
                        f"{status_emoji} الحالة: {req.status}\n"
                        f"👥 الأعضاء: {req.requested_members}\n"
                        f"💰 التكلفة: {req.points_cost} نقطة\n"
                        f"🕒 الوقت: {req.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                        f"────────────────────\n"
                    )
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_transfer_history(self, query, context):
        """عرض سجل تحويلات المستخدم"""
        db = self.db()
        try:
            user_id = query.from_user.id
            transfers = db.query(PointsTransfer).filter(
                (PointsTransfer.from_user_id == user_id) | (PointsTransfer.to_user_id == user_id)
            ).order_by(PointsTransfer.transfer_date.desc()).limit(10).all()
            
            if not transfers:
                text = "📋 لا توجد تحويلات سابقة."
            else:
                text = "📋 آخر 10 تحويلات:\n\n"
                for transfer in transfers:
                    if transfer.from_user_id == user_id:
                        direction = "📤 مرسل"
                        target = transfer.to_user_id
                    else:
                        direction = "📥 مستلم"
                        target = transfer.from_user_id
                    
                    text += (
                        f"{direction}\n"
                        f"💰 المبلغ: {transfer.amount} نقطة\n"
                        f"💸 العمولة: {transfer.fee_amount} نقطة\n"
                        f"👤 الطرف الآخر: {target}\n"
                        f"🕒 الوقت: {transfer.transfer_date.strftime('%Y-%m-%d %H:%M')}\n"
                        f"────────────────────\n"
                    )
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="transfer_points")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def give_daily_gift(self, query, context):
        """منح الهدية اليومية"""
        db = self.db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            now = datetime.now()
            
            # التحقق إذا أخذ الهدية اليوم
            if user.last_daily_gift:
                last_gift_date = user.last_daily_gift.date()
                if last_gift_date == now.date():
                    next_gift = user.last_daily_gift + timedelta(days=1)
                    remaining = next_gift - now
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    
                    await query.answer(f"⏳ الهدية متاحة بعد {hours} ساعة و {minutes} دقيقة", show_alert=True)
                    return
            
            # منح النقاط
            points_settings = db.query(PointsSettings).first()
            points = points_settings.daily_gift_points if points_settings else self.config.DAILY_GIFT_POINTS
            
            user.points += points
            user.last_daily_gift = now
            db.commit()
            
            await query.answer(f"🎁 حصلت على {points} نقاط!", show_alert=True)
            await self.show_my_points(query, context)
        finally:
            db.close()
    
    # ==================== 📝 معالجة الرسائل النصية ====================
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الرسائل النصية"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # التحقق من وضع الصيانة
        if await self.check_maintenance(update):
            return
        
        # إذا كان المستخدم في مرحلة إدخال عدد الأعضاء
        if 'funding_type' in context.user_data and 'requested_members' not in context.user_data:
            await self.handle_funding_request(update, context)
        
        # إذا كان المستخدم في مرحلة إدخال الرابط
        elif 'requested_members' in context.user_data and 'points_needed' in context.user_data:
            await self.handle_channel_link(update, context)
        
        # إذا كان طلب تحويل نقاط
        elif text.startswith('تحويل '):
            await self.handle_points_transfer(update, context)
        
        # إذا كان رسالة عادية
        else:
            # التحقق من الاشتراك الإجباري أولاً
            if not await self.check_mandatory_channels(user_id, context):
                await update.message.reply_text("⛔ يجب الاشتراك في القنوات الإجبارية أولاً! استخدم /start")
                return
            
            # إذا كان المستخدم مشرف ويرسل أمر
            db = self.db()
            try:
                user = db.query(User).filter_by(user_id=user_id).first()
                if user and user.is_admin and text.startswith('/'):
                    await self.handle_admin_commands(update, context)
                else:
                    await update.message.reply_text("استخدم الأزرار في القائمة أو /start للبدء")
            finally:
                db.close()
    
    async def handle_funding_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة طلب التمويل"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if not text.isdigit():
            await update.message.reply_text("❌ الرجاء إدخال رقم صحيح!")
            return
        
        requested_members = int(text)
        db = self.db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else self.config.POINTS_PER_MEMBER
            
            # حساب التكلفة
            points_needed = requested_members * points_per_member
            
            if user.points < points_needed:
                await update.message.reply_text(
                    f"❌ نقاطك غير كافية!\n"
                    f"💎 لديك: {user.points} نقطة\n"
                    f"💰 تحتاج: {points_needed} نقطة\n"
                    f"⭐ الناقص: {points_needed - user.points} نقطة"
                )
                return
            
            context.user_data['requested_members'] = requested_members
            context.user_data['points_needed'] = points_needed
            
            await update.message.reply_text(
                f"✅ الطلب مقبول!\n"
                f"📊 عدد الأعضاء: {requested_members}\n"
                f"💰 التكلفة: {points_needed} نقطة\n\n"
                f"📝 الآن ارسل رابط قناتك/مجموعتك:\n"
                f"(يبدأ بـ @ أو https://t.me/)"
            )
        finally:
            db.close()
    
    async def handle_channel_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة رابط القناة"""
        user_id = update.effective_user.id
        link = update.message.text
        db = self.db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user or 'requested_members' not in context.user_data:
                return
            
            # استخراج معرف القناة
            channel_id = self.extract_channel_id(link)
            if not channel_id:
                await update.message.reply_text("❌ رابط غير صالح! تأكد من الرابط وأرسله مرة أخرى.")
                return
            
            # التحقق من أن البوت أدمن في القناة
            try:
                chat_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                if chat_member.status not in ['administrator', 'creator']:
                    await update.message.reply_text("❌ البوت ليس أدمن في القناة! ارفع البوت كأدمن أولاً.")
                    return
            except Exception as e:
                print(f"Error checking admin status: {e}")
                await update.message.reply_text("❌ لا يمكن الوصول للقناة! تأكد من صلاحيات البوت.")
                return
            
            # خصم النقاط وإنشاء الطلب
            requested_members = context.user_data['requested_members']
            points_needed = context.user_data['points_needed']
            
            user.points -= points_needed
            funding_request = FundingRequest(
                user_id=user_id,
                target_channel=channel_id,
                target_type=context.user_data['funding_type'],
                requested_members=requested_members,
                points_cost=points_needed,
                status='pending',
                created_at=datetime.now()
            )
            
            db.add(funding_request)
            db.commit()
            
            # إرسال إشعار للمشرفين
            await self.notify_admins_about_request(context.bot, funding_request, user)
            
            await update.message.reply_text(
                f"✅ تم استلام طلبك!\n"
                f"📊 رقم الطلب: {funding_request.id}\n"
                f"👥 الأعضاء: {requested_members}\n"
                f"💰 النقاط المخصومة: {points_needed}\n"
                f"⭐ نقاطك المتبقية: {user.points}\n\n"
                f"⏳ الطلب قيد الانتظار للموافقة..."
            )
            
            # تنظيف البيانات المؤقتة
            context.user_data.clear()
            
        finally:
            db.close()
    
    async def handle_points_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة طلب تحويل النقاط"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        db = self.db()
        
        try:
            # التحقق من صيغة الرسالة
            if not text.startswith('تحويل '):
                return
            
            parts = text.split()
            if len(parts) != 3:
                await update.message.reply_text("❌ صيغة خاطئة! استخدم: `تحويل [المبلغ] [إيدي المستخدم]`")
                return
            
            amount = int(parts[1])
            target_user_id = int(parts[2])
            
            # التحقق من الإعدادات
            settings = db.query(SystemSettings).first()
            if not settings or not settings.transfer_enabled:
                await update.message.reply_text("❌ خدمة تحويل النقاط معطلة حالياً!")
                return
            
            # منع التحويل للنفس
            if target_user_id == user_id:
                await update.message.reply_text("❌ لا يمكنك تحويل النقاط لنفسك!")
                return
            
            # جلب بيانات المرسل
            sender = db.query(User).filter_by(user_id=user_id).first()
            if not sender:
                await update.message.reply_text("❌ حسابك غير موجود!")
                return
            
            # التحقق من الرصيد
            fee_percent = settings.transfer_fee_percent
            fee_amount = int(amount * fee_percent / 100)
            total_deduct = amount + fee_amount
            
            if sender.points < total_deduct:
                await update.message.reply_text(
                    f"❌ نقاطك غير كافية!\n"
                    f"💎 تحتاج: {total_deduct} نقطة (المبلغ + العمولة)\n"
                    f"⭐ لديك: {sender.points} نقطة"
                )
                return
            
            # جلب بيانات المستقبل
            receiver = db.query(User).filter_by(user_id=target_user_id).first()
            if not receiver:
                await update.message.reply_text("❌ المستخدم الهدف غير موجود!")
                return
            
            # تنفيذ التحويل
            sender.points -= total_deduct
            receiver.points += amount
            
            # تسجيل العملية
            transfer = PointsTransfer(
                from_user_id=user_id,
                to_user_id=target_user_id,
                amount=amount,
                fee_percent=fee_percent,
                fee_amount=fee_amount,
                net_amount=amount,
                transfer_date=datetime.now()
            )
            db.add(transfer)
            db.commit()
            
            # إرسال إشعارات
            await update.message.reply_text(
                f"✅ تم تحويل {amount} نقطة بنجاح!\n\n"
                f"📤 إلى: {receiver.first_name or 'مستخدم'} (إيدي: {target_user_id})\n"
                f"💸 العمولة: {fee_amount} نقطة ({fee_percent}%)\n"
                f"💰 المبلغ الإجمالي: {total_deduct} نقطة\n"
                f"⭐ رصيدك الجديد: {sender.points} نقطة"
            )
            
            # إشعار المستقبل
            try:
                await context.bot.send_message(
                    target_user_id,
                    f"🎉 استلمت تحويل نقاط!\n\n"
                    f"📥 من: {sender.first_name or 'مستخدم'} (إيدي: {user_id})\n"
                    f"💰 المبلغ: {amount} نقطة\n"
                    f"⭐ رصيدك الجديد: {receiver.points} نقطة"
                )
            except:
                pass  # قد يكون المستقبل حظر البوت
            
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال أرقام صحيحة!")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        finally:
            db.close()
    
    # ==================== 👑 أوامر المشرفين ====================
    async def handle_admin_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أوامر المشرفين"""
        text = update.message.text
        user_id = update.effective_user.id
        db = self.db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user or not user.is_admin:
                return
            
            if text.startswith('/add_admin'):
                await self.handle_add_admin(update, context, text)
            
            elif text.startswith('/ban'):
                await self.handle_ban_user(update, context, text)
            
            elif text.startswith('/add_points'):
                await self.handle_add_points(update, context, text)
            
            elif text.startswith('/maintenance'):
                await self.handle_maintenance(update, context, text)
            
            elif text.startswith('/set_fee'):
                await self.handle_set_fee(update, context, text)
            
            elif text.startswith('/add_support'):
                await self.handle_add_support(update, context, text)
            
            elif text.startswith('/remove_support'):
                await self.handle_remove_support(update, context, text)
            
            elif text.startswith('/add_channel'):
                await self.handle_add_channel(update, context, text)
            
            elif text.startswith('/add_group'):
                await self.handle_add_group(update, context, text)
        
        finally:
            db.close()
    
    async def handle_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إضافة مشرف جديد"""
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ صيغة خاطئة: /add_admin @username أو user_id")
            return
        
        target = parts[1].replace('@', '')
        db = self.db()
        
        try:
            if target.isdigit():
                target_user = db.query(User).filter_by(user_id=int(target)).first()
            else:
                target_user = db.query(User).filter_by(username=target).first()
            
            if not target_user:
                await update.message.reply_text("❌ المستخدم غير موجود!")
                return
            
            target_user.is_admin = True
            db.commit()
            
            await update.message.reply_text(f"✅ تمت ترقية {target_user.first_name} إلى مشرف")
        finally:
            db.close()
    
    async def handle_ban_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """حظر مستخدم"""
        parts = text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ صيغة خاطئة: /ban @username السبب")
            return
        
        target = parts[1].replace('@', '')
        reason = ' '.join(parts[2:])
        db = self.db()
        
        try:
            if target.isdigit():
                target_user = db.query(User).filter_by(user_id=int(target)).first()
            else:
                target_user = db.query(User).filter_by(username=target).first()
            
            if not target_user:
                await update.message.reply_text("❌ المستخدم غير موجود!")
                return
            
            target_user.is_banned = True
            target_user.ban_reason = reason
            db.commit()
            
            await update.message.reply_text(f"✅ تم حظر {target_user.first_name}\nالسبب: {reason}")
        finally:
            db.close()
    
    async def handle_add_points(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إضافة نقاط لمستخدم"""
        parts = text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ صيغة خاطئة: /add_points @username العدد")
            return
        
        target = parts[1].replace('@', '')
        points = int(parts[2])
        db = self.db()
        
        try:
            if target.isdigit():
                target_user = db.query(User).filter_by(user_id=int(target)).first()
            else:
                target_user = db.query(User).filter_by(username=target).first()
            
            if not target_user:
                await update.message.reply_text("❌ المستخدم غير موجود!")
                return
            
            target_user.points += points
            db.commit()
            
            await update.message.reply_text(f"✅ تم إضافة {points} نقطة لـ {target_user.first_name}")
        finally:
            db.close()
    
    async def handle_maintenance(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """تفعيل/تعطيل وضع الصيانة"""
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ صيغة خاطئة: /maintenance on/off [رسالة]")
            return
        
        mode = parts[1].lower()
        message = ' '.join(parts[2:]) if len(parts) > 2 else "🔧 البوت تحت الصيانة حالياً"
        
        db = self.db()
        try:
            settings = db.query(SystemSettings).first()
            if settings:
                if mode == 'on':
                    settings.maintenance_mode = True
                    settings.maintenance_message = message
                    await update.message.reply_text(f"✅ تم تفعيل وضع الصيانة\n📝 الرسالة: {message}")
                elif mode == 'off':
                    settings.maintenance_mode = False
                    await update.message.reply_text("✅ تم تعطيل وضع الصيانة")
                db.commit()
        finally:
            db.close()
    
    async def handle_set_fee(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """تعديل عمولة التحويل"""
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ صيغة خاطئة: /set_fee النسبة")
            return
        
        try:
            fee = int(parts[1])
            if fee < 0 or fee > 50:
                await update.message.reply_text("❌ النسبة يجب أن تكون بين 0 و 50!")
                return
            
            db = self.db()
            try:
                settings = db.query(SystemSettings).first()
                if settings:
                    old_fee = settings.transfer_fee_percent
                    settings.transfer_fee_percent = fee
                    db.commit()
                    await update.message.reply_text(f"✅ تم تغيير عمولة التحويل من {old_fee}% إلى {fee}%")
            finally:
                db.close()
        except ValueError:
            await update.message.reply_text("❌ الرجاء إدخال رقم صحيح!")
    
    async def handle_add_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إضافة ممثل دعم"""
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ صيغة خاطئة: /add_support @username")
            return
        
        target = parts[1].replace('@', '')
        
        # البحث عن المستخدم
        try:
            user = await context.bot.get_chat(target)
            
            db = self.db()
            try:
                # التحقق إذا موجود مسبقاً
                existing = db.query(SupportContact).filter_by(user_id=user.id).first()
                if existing:
                    await update.message.reply_text("⚠️ هذا المستخدم مضاف بالفعل للدعم!")
                    return
                
                # إضافة ممثل دعم جديد
                support = SupportContact(
                    user_id=user.id,
                    username=user.username or user.first_name,
                    added_by=update.effective_user.id,
                    added_at=datetime.now()
                )
                db.add(support)
                db.commit()
                
                await update.message.reply_text(f"✅ تم إضافة @{user.username or user.first_name} كممثل دعم")
            finally:
                db.close()
                
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}")
    
    async def handle_remove_support(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إزالة ممثل دعم"""
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ صيغة خاطئة: /remove_support @username")
            return
        
        target = parts[1].replace('@', '')
        db = self.db()
        
        try:
            support = db.query(SupportContact).filter_by(username=target).first()
            if not support:
                await update.message.reply_text("❌ ممثل الدعم غير موجود!")
                return
            
            db.delete(support)
            db.commit()
            
            await update.message.reply_text(f"✅ تم إزالة @{target} من قائمة الدعم")
        finally:
            db.close()
    
    async def handle_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إضافة قناة إجبارية"""
        parts = text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ صيغة خاطئة: /add_channel @channel_id عنوان_القناة [mandatory/optional]")
            return
        
        channel_id = parts[1]
        channel_title = ' '.join(parts[2:-1]) if len(parts) > 3 else parts[2]
        is_mandatory = parts[-1].lower() == 'mandatory' if len(parts) > 3 else False
        
        db = self.db()
        try:
            # التحقق إذا القناة موجودة مسبقاً
            existing = db.query(Channel).filter_by(channel_id=channel_id).first()
            if existing:
                await update.message.reply_text("⚠️ هذه القناة مضافه بالفعل!")
                return
            
            # إضافة القناة
            channel = Channel(
                channel_id=channel_id,
                channel_title=channel_title,
                is_mandatory=is_mandatory,
                added_by_admin=update.effective_user.id,
                created_at=datetime.now()
            )
            db.add(channel)
            db.commit()
            
            status = "إجبارية" if is_mandatory else "اختيارية"
            await update.message.reply_text(f"✅ تم إضافة القناة {channel_title}\n📢 الحالة: {status}")
        finally:
            db.close()
    
    async def handle_add_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """إضافة مجموعة مصدر"""
        parts = text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ صيغة خاطئة: /add_group @group_id عنوان_المجموعة")
            return
        
        group_id = parts[1]
        group_title = ' '.join(parts[2:])
        
        db = self.db()
        try:
            # التحقق إذا المجموعة موجودة مسبقاً
            existing = db.query(GroupSource).filter_by(group_id=group_id).first()
            if existing:
                await update.message.reply_text("⚠️ هذه المجموعة مضافه بالفعل!")
                return
            
            # إضافة المجموعة
            group = GroupSource(
                group_id=group_id,
                group_title=group_title,
                added_by_admin=update.effective_user.id,
                created_at=datetime.now()
            )
            db.add(group)
            db.commit()
            
            await update.message.reply_text(f"✅ تم إضافة المجموعة {group_title}")
        finally:
            db.close()
    
    # ==================== 📋 لوحة تحكم المشرفين ====================
    async def show_admin_panel(self, query, context):
        """عرض لوحة تحكم المشرف"""
        db = self.db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user or not user.is_admin:
                await query.answer("❌ ليس لديك صلاحية الدخول!", show_alert=True)
                return
            
            text = """
👑 لوحة تحكم المشرف

اختر القسم:
"""
            
            keyboard = [
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
                [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="admin_users")],
                [InlineKeyboardButton("👑 إدارة المشرفين", callback_data="admin_admins")],
                [InlineKeyboardButton("📢 إدارة القنوات", callback_data="admin_channels")],
                [InlineKeyboardButton("👥 إدارة المجموعات", callback_data="admin_groups")],
                [InlineKeyboardButton("📋 طلبات التمويل", callback_data="admin_requests")],
                [InlineKeyboardButton("📞 إدارة الدعم", callback_data="admin_support")],
                [InlineKeyboardButton("⚙️ إعدادات النظام", callback_data="admin_system")],
                [InlineKeyboardButton("⭐ إعدادات النقاط", callback_data="admin_points")],
                [InlineKeyboardButton("🔄 إعدادات التحويل", callback_data="admin_transfer")],
                [InlineKeyboardButton("📨 إرسال للجميع", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    # ==================== 🔔 الإشعارات ====================
    async def notify_admins_about_request(self, bot, request, user):
        """إرسال إشعار للمشرفين بطلب جديد"""
        db = self.db()
        try:
            admins = db.query(User).filter_by(is_admin=True).all()
            
            for admin in admins:
                try:
                    text = f"""
📋 طلب تمويل جديد!

👤 المستخدم: {user.first_name or 'مجهول'}
🆔 الإيدي: {user.user_id}
📊 رقم الطلب: {request.id}
👥 عدد الأعضاء: {request.requested_members}
💰 التكلفة: {request.points_cost} نقطة
📢 الهدف: {request.target_channel}
🕒 الوقت: {request.created_at.strftime('%Y-%m-%d %H:%M:%S')}
"""
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("✅ قبول", callback_data=f"approve_request_{request.id}"),
                            InlineKeyboardButton("❌ رفض", callback_data=f"reject_request_{request.id}")
                        ]
                    ]
                    
                    await bot.send_message(
                        admin.user_id,
                        text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except:
                    pass
        finally:
            db.close()
    
    # ==================== 🚀 نظام إضافة الأعضاء ====================
    class MemberAdder:
        """فئة لإضافة الأعضاء من المجموعات"""
        
        def __init__(self, bot):
            self.bot = bot
        
        async def add_members_to_channel(self, request_id: int):
            """إضافة أعضاء للقناة من المجموعات المصدر"""
            db = get_db()
            try:
                request = db.query(FundingRequest).filter_by(id=request_id).first()
                if not request or request.status != 'approved':
                    return
                
                user = db.query(User).filter_by(user_id=request.user_id).first()
                if not user:
                    return
                
                target_channel = request.target_channel
                needed_members = request.requested_members
                added_count = 0
                
                print(f"🚀 بدء إضافة {needed_members} عضو للقناة {target_channel}")
                
                # إعلام المستخدم بالبدء
                try:
                    await self.bot.send_message(
                        user.user_id,
                        f"🚀 بدأت عملية إضافة الأعضاء لطلبك #{request_id}\n"
                        f"👥 العدد المطلوب: {needed_members} عضو"
                    )
                except:
                    pass
                
                # الحصول على المجموعات المصدر النشطة
                source_groups = db.query(GroupSource).filter_by(is_active=True).all()
                
                for group in source_groups:
                    if added_count >= needed_members:
                        break
                    
                    try:
                        # جلب أعضاء المجموعة
                        members_added = await self.add_members_from_group(
                            group.group_id,
                            target_channel,
                            needed_members - added_count
                        )
                        
                        added_count += members_added
                        print(f"✅ تمت إضافة {members_added} عضو من مجموعة {group.group_title}")
                        
                        # تحديث حالة الطلب
                        request.completed_members = added_count
                        db.commit()
                        
                        # تأخير بين المجموعات
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        print(f"❌ خطأ في المجموعة {group.group_id}: {e}")
                        continue
                
                # تحديث الحالة النهائية
                if added_count > 0:
                    request.status = 'completed'
                    success_message = f"✅ تم الانتهاء من طلبك #{request.id}\n👥 تمت إضافة {added_count} عضو بنجاح!"
                else:
                    request.status = 'failed'
                    success_message = f"❌ فشل طلبك #{request.id}\n⚠️ لم تتم إضافة أي عضو."
                
                db.commit()
                
                # إعلام المستخدم
                try:
                    await self.bot.send_message(user.user_id, success_message)
                except:
                    pass
                
                return added_count
                
            except Exception as e:
                print(f"❌ خطأ في إضافة الأعضاء: {e}")
                return 0
            finally:
                db.close()
        
        async def add_members_from_group(self, source_group_id: str, target_channel: str, max_members: int):
            """إضافة أعضاء من مجموعة مصدر معينة"""
            added_count = 0
            
            try:
                # جلب قائمة الأعضاء (بحدود معينة)
                members = await self.get_group_members(source_group_id, max_members * 2)
                
                print(f"📋 جاري معالجة {len(members)} عضو من المجموعة {source_group_id}")
                
                for member in members:
                    if added_count >= max_members:
                        break
                    
                    try:
                        # محاولة إضافة العضو للقناة
                        await self.bot.add_chat_members(
                            chat_id=target_channel,
                            user_ids=[member.user.id]
                        )
                        
                        added_count += 1
                        print(f"✅ تمت إضافة العضو {member.user.id}")
                        
                        # تأخير بين كل إضافة لتجنب الحظر
                        await asyncio.sleep(Config.ADD_MEMBERS_DELAY)
                        
                    except UserPrivacyRestrictedError:
                        print(f"⚠️ العضو {member.user.id} مقيد الخصوصية")
                        continue
                        
                    except TelegramError as e:
                        if "USER_ALREADY_PARTICIPANT" in str(e):
                            print(f"✅ العضو {member.user.id} موجود بالفعل")
                            added_count += 1
                        elif "USER_NOT_MUTUAL_CONTACT" in str(e):
                            print(f"⚠️ العضو {member.user.id} ليس جهة اتصال متبادلة")
                        elif "CHAT_ADMIN_REQUIRED" in str(e):
                            print(f"❌ البوت ليس أدمن في القناة الهدف")
                            break
                        else:
                            print(f"⚠️ خطأ في إضافة العضو {member.user.id}: {e}")
                        continue
                    except Exception as e:
                        print(f"❌ خطأ غير متوقع: {e}")
                        continue
            
            except Exception as e:
                print(f"❌ خطأ في جلب أعضاء المجموعة {source_group_id}: {e}")
            
            return added_count
        
        async def get_group_members(self, group_id: str, limit: int = 100):
            """جلب قائمة أعضاء المجموعة"""
            members = []
            
            try:
                # جلب الأعضاء من المجموعة
                async for member in self.bot.get_chat_members(group_id):
                    if len(members) >= limit:
                        break
                    
                    # استبعاد البوتات والمشرفين
                    if not member.user.is_bot and member.status == 'member':
                        members.append(member)
            
            except Exception as e:
                print(f"❌ خطأ في جلب أعضاء المجموعة: {e}")
            
            return members
    
    # ==================== 🔄 معالجة الطلبات في الخلفية ====================
    async def process_pending_requests(self, bot):
        """معالجة طلبات التمويل المعلقة في الخلفية"""
        adder = self.MemberAdder(bot)
        print("🔄 بدء معالج طلبات التمويل...")
        
        while True:
            try:
                db = get_db()
                
                # البحث عن طلبات معتمدة تحتاج معالجة
                pending_requests = db.query(FundingRequest).filter_by(status='approved').all()
                
                print(f"📋 وجدت {len(pending_requests)} طلب معتمد للمعالجة")
                
                for request in pending_requests:
                    print(f"⚙️ معالجة الطلب #{request.id}")
                    await adder.add_members_to_channel(request.id)
                
                db.close()
                
                # انتظار 5 دقائق بين كل جولة
                await asyncio.sleep(300)
                
            except Exception as e:
                print(f"❌ خطأ في معالجة الطلبات: {e}")
                await asyncio.sleep(60)
    
    # ==================== 🚀 تشغيل البوت ====================
    async def run(self):
        """تشغيل البوت"""
        # التحقق من التوكن
        if self.config.BOT_TOKEN == "ضع_توكن_البوت_هنا":
            print("❌ خطأ: لم تقم بوضع توكن البوت!")
            print("🔧 قم بتعديل التوكن في الكود")
            return
        
        # تهيئة قاعدة البيانات
        print("🔄 جاري تهيئة قاعدة البيانات...")
        init_database()
        
        # بدء خدمات البقاء نشط
        self.keep_alive.start_keep_alive_server()
        print("✅ تم تشغيل خدمات البقاء نشط")
        
        # إنشاء تطبيق البوت
        print("🤖 جاري إنشاء تطبيق البوت...")
        self.application = Application.builder().token(self.config.BOT_TOKEN).build()
        
        # إضافة المعالجات
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        # معالجة الرسائل النصية
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # بدء البوت
        print("🚀 جاري تشغيل البوت...")
        print(f"👑 المدير الرئيسي: {self.config.ADMIN_ID}")
        print(f"🤖 اسم البوت: @{(await self.application.bot.get_me()).username}")
        
        # بدء معالجة الطلبات في الخلفية
        asyncio.create_task(self.process_pending_requests(self.application.bot))
        
        # بدء مجدول البقاء نشط
        self.keep_alive.start_scheduler(self.application.bot)
        
        # بدء الاستماع للتحديثات
        await self.application.run_polling(allowed_updates="all")

# ==================== 📦 التشغيل الرئيسي ====================
if __name__ == '__main__':
    # إعداد التسجيل
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # إنشاء وتشغيل البوت
    bot = TelegramFundingBot()
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت")
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")