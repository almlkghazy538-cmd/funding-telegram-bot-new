"""
🤖 بوت تمويل القنوات - النسخة النهائية المصححة
"""

# ==================== 📥 استيراد المكتبات ====================
import os
import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from threading import Thread
import requests
import sys

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError  # ✅ تم التصحيح

from sqlalchemy import create_engine, Column, Integer, String, Boolean, BigInteger, DateTime, Text, func, desc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

# ==================== ⚙️ الإعدادات ====================
class Config:
    """إعدادات البوت"""
    BOT_TOKEN = "8436742877:AAGhCfnC9hbW7Sa4gMTroYissoljCjda9Ow"
    ADMIN_ID = 6130994941
    DATABASE_URL = "sqlite:///bot_database.db"
    
    # إعدادات النظام
    MAINTENANCE_MODE = False
    MAINTENANCE_MESSAGE = "🔧 البوت تحت الصيانة"
    TRANSFER_FEE_PERCENT = 5
    TRANSFER_ENABLED = True
    
    # إعدادات النقاط
    POINTS_PER_REFERRAL = 5
    DAILY_GIFT_POINTS = 3
    POINTS_PER_CHANNEL_SUB = 2
    MIN_POINTS_FOR_FUNDING = 25
    POINTS_PER_MEMBER = 25
    
    # إعدادات الأداء
    MAX_MEMBERS_PER_REQUEST = 50
    ADD_MEMBERS_DELAY = 1
    PORT = 8080

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
    maintenance_message = Column(Text, default='🔧 البوت تحت الصيانة')
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
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()

def init_database():
    db = get_db()
    try:
        if db.query(SystemSettings).count() == 0:
            settings = SystemSettings()
            db.add(settings)
        
        if db.query(PointsSettings).count() == 0:
            points_settings = PointsSettings()
            db.add(points_settings)
        
        admin_user = db.query(User).filter_by(user_id=Config.ADMIN_ID).first()
        if not admin_user:
            admin_user = User(
                user_id=Config.ADMIN_ID,
                username="admin",
                first_name="👑 المدير",
                is_admin=True,
                admin_permissions='["all"]'
            )
            db.add(admin_user)
        
        db.commit()
        print("✅ تم تهيئة قاعدة البيانات")
        return True
    except Exception as e:
        print(f"❌ خطأ في قاعدة البيانات: {e}")
        db.rollback()
        return False
    finally:
        db.close()

# ==================== 🔄 نظام البقاء نشط ====================
class KeepAliveSystem:
    """نظام البقاء نشط 24/7"""
    
    def __init__(self, bot_token, admin_id):
        self.bot_token = bot_token
        self.admin_id = admin_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    def start_web_server(self):
        """تشغيل خادم ويب لـ Render"""
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return "🤖 البوت يعمل | " + datetime.now().strftime("%H:%M:%S")
        
        @app.route('/health')
        def health():
            return {"status": "active", "time": datetime.now().isoformat()}
        
        def run():
            app.run(host='0.0.0.0', port=Config.PORT, debug=False)
        
        server_thread = Thread(target=run, daemon=True)
        server_thread.start()
        print(f"✅ خادم ويب يعمل على بورت {Config.PORT}")
    
    async def send_ping(self):
        """إرسال إشارة للمدير"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.admin_id,
                'text': f"🟢 ping | {datetime.now().strftime('%H:%M')}",
                'disable_notification': True
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                print(f"✅ إشارة ping أرسلت: {datetime.now().strftime('%H:%M:%S')}")
        except:
            pass
    
    def start_ping_scheduler(self, bot):
        """بدء إشارات ping دورية"""
        async def ping_job():
            await self.send_ping()
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: asyncio.run(ping_job()), 'interval', minutes=2)
        scheduler.start()
        print("✅ مجدول ping يعمل (كل دقيقتين)")

# ==================== 🤖 البوت الرئيسي ====================
class TelegramBot:
    def __init__(self):
        self.config = Config
        self.keep_alive = KeepAliveSystem(Config.BOT_TOKEN, Config.ADMIN_ID)
        self.application = None
    
    # ==================== 🔧 دوال مساعدة ====================
    def extract_channel_id(self, link: str):
        if link.startswith('@'):
            return link
        elif 't.me/' in link:
            parts = link.split('t.me/')
            if len(parts) > 1:
                channel_part = parts[1].split('/')[0]
                return '@' + channel_part
        return None
    
    async def check_mandatory_channels(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        db = get_db()
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
    
    # ==================== 👤 تسجيل المستخدم ====================
    async def register_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        db = get_db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if user:
                return user
            
            user = User(
                user_id=user_id,
                username=update.effective_user.username or "",
                first_name=update.effective_user.first_name or "",
                last_name=update.effective_user.last_name or "",
                created_at=datetime.now()
            )
            
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
        except:
            return None
        finally:
            db.close()
    
    # ==================== 🎯 أمر /start ====================
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not await self.check_mandatory_channels(user_id, context):
            await self.show_mandatory_channels_start(update, context)
            return
        
        user = await self.register_user(update, context)
        if not user:
            await update.message.reply_text("❌ خطأ في التسجيل")
            return
        
        if user.is_banned:
            await update.message.reply_text(f"🚫 حسابك محظور\nالسبب: {user.ban_reason}")
            return
        
        await self.show_main_menu(update, context, user)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user):
        welcome_text = f"""
👋 أهلاً {user.first_name}!

🆔 إيديك: `{user.user_id}`
⭐ نقاطك: {user.points:,}
📊 دعواتك: {user.referrals}

اختر من القائمة:
"""
        
        keyboard = []
        if user.is_admin:
            keyboard.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin_panel")])
        
        keyboard.extend([
            [InlineKeyboardButton("👥 زيادة المشتركين", callback_data="increase_members")],
            [InlineKeyboardButton("⭐ نقاطي", callback_data="my_points")],
            [InlineKeyboardButton("🔄 تحويل النقاط", callback_data="transfer_points")],
            [InlineKeyboardButton("📢 قنوات إجبارية", callback_data="mandatory_channels")],
            [InlineKeyboardButton("📞 الدعم", callback_data="contact_support")],
            [InlineKeyboardButton("🔗 رابط الدعوة", callback_data="invite_link")],
            [InlineKeyboardButton("🎁 هدية يومية", callback_data="daily_gift")]
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
    
    async def show_mandatory_channels_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        db = get_db()
        try:
            channels = db.query(Channel).filter_by(is_mandatory=True).all()
            if not channels:
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
                "⚠️ اشترك في القنوات التالية أولاً:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    # ==================== 🔘 معالجة الأزرار ====================
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
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
        elif data == "check_subscription":
            await self.handle_check_subscription(query, context)
        elif data == "back_to_main":
            await self.back_to_main_menu(query, context)
        elif data.startswith("funding_type_"):
            await self.handle_funding_type(query, context, data)
    
    async def show_admin_panel(self, query, context):
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user or not user.is_admin:
                await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
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
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_increase_members(self, query, context):
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            min_points = points_settings.min_points_for_funding if points_settings else 25
            
            if user.points < min_points:
                await query.answer(f"❌ تحتاج {min_points} نقطة على الأقل!", show_alert=True)
                return
            
            keyboard = [
                [InlineKeyboardButton("📢 قناة عامة", callback_data="funding_type_channel")],
                [InlineKeyboardButton("👥 مجموعة", callback_data="funding_type_group")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(
                "اختر نوع القناة/المجموعة:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_my_points(self, query, context):
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            
            points_text = f"""
⭐ نقاطك الحالية: {user.points:,}

طرق زيادة النقاط:
1. 🔗 دعوة أصدقاء: {points_settings.points_per_referral if points_settings else 5} نقاط
2. 📢 الاشتراك في القنوات: {points_settings.points_per_channel if points_settings else 2} نقاط
3. 🎁 الهدية اليومية: {points_settings.daily_gift_points if points_settings else 3} نقاط
4. 💰 شراء النقاط: تواصل مع الدعم

أقل حد للتمويل: {points_settings.min_points_for_funding if points_settings else 25} نقطة
"""
            
            keyboard = [
                [InlineKeyboardButton("🔄 تحويل النقاط", callback_data="transfer_points")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]
            ]
            
            await query.edit_message_text(points_text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_transfer_points(self, query, context):
        db = get_db()
        try:
            settings = db.query(SystemSettings).first()
            if not settings or not settings.transfer_enabled:
                await query.answer("❌ خدمة التحويل معطلة!", show_alert=True)
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
                f"⭐ نقاطك: {user.points:,}\n"
                f"💸 عمولة: {settings.transfer_fee_percent}%\n"
                f"اختر الإجراء:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    async def show_mandatory_channels_menu(self, query, context):
        db = get_db()
        try:
            channels = db.query(Channel).filter_by(is_mandatory=True).all()
            
            if not channels:
                text = "✅ لا توجد قنوات إجبارية"
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
        db = get_db()
        try:
            support_contacts = db.query(SupportContact).filter_by(is_active=True).all()
            
            if not support_contacts:
                text = "📞 لا يوجد ممثلين للدعم"
            else:
                text = "📞 قائمة الدعم:\n\n"
                for contact in support_contacts:
                    text += f"• @{contact.username}\n"
                text += "\nراسل أي ممثل للشحن أو الاستفسار"
            
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_invite_link(self, query, context):
        bot_username = context.bot.username
        invite_link = f"https://t.me/{bot_username}?start={query.from_user.id}"
        
        db = get_db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_referral = points_settings.points_per_referral if points_settings else 5
            
            text = f"""
🔗 رابط دعوتك:

`{invite_link}`

📊 لكل صديق تدعوه: {points_per_referral} نقاط
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
    
    async def give_daily_gift(self, query, context):
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            now = datetime.now()
            
            if user.last_daily_gift:
                last_gift_date = user.last_daily_gift.date()
                if last_gift_date == now.date():
                    next_gift = user.last_daily_gift + timedelta(days=1)
                    remaining = next_gift - now
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    
                    await query.answer(f"⏳ متاح بعد {hours}س {minutes}د", show_alert=True)
                    return
            
            points_settings = db.query(PointsSettings).first()
            points = points_settings.daily_gift_points if points_settings else 3
            
            user.points += points
            user.last_daily_gift = now
            db.commit()
            
            await query.answer(f"🎁 حصلت على {points} نقاط!", show_alert=True)
            await self.show_my_points(query, context)
        finally:
            db.close()
    
    async def handle_check_subscription(self, query, context):
        if await self.check_mandatory_channels(query.from_user.id, context):
            db = get_db()
            try:
                user = db.query(User).filter_by(user_id=query.from_user.id).first()
                if user:
                    await self.show_main_menu(update, context, user)
            finally:
                db.close()
        else:
            await query.answer("❌ لم تشترك في كل القنوات!", show_alert=True)
    
    async def back_to_main_menu(self, query, context):
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if user:
                await self.show_main_menu(update, context, user)
        finally:
            db.close()
    
    async def handle_funding_type(self, query, context, data):
        funding_type = data.split("_")[2]
        context.user_data['funding_type'] = funding_type
        
        db = get_db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else 25
            
            await query.edit_message_text(
                f"📝 ارسل عدد الأعضاء ({funding_type}):\n\n"
                f"💎 سعر العضو: {points_per_member} نقطة\n"
                f"💰 احسب: (العدد × {points_per_member})"
            )
        finally:
            db.close()
    
    # ==================== 📝 معالجة الرسائل ====================
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        if 'funding_type' in context.user_data and 'requested_members' not in context.user_data:
            await self.handle_funding_request(update, context)
        elif 'requested_members' in context.user_data and 'points_needed' in context.user_data:
            await self.handle_channel_link(update, context)
        elif text.startswith('تحويل '):
            await self.handle_points_transfer(update, context)
        else:
            if not await self.check_mandatory_channels(user_id, context):
                await update.message.reply_text("⛔ اشترك في القنوات أولاً! /start")
                return
            
            db = get_db()
            try:
                user = db.query(User).filter_by(user_id=user_id).first()
                if user and user.is_admin and text.startswith('/'):
                    await self.handle_admin_commands(update, context)
                else:
                    await update.message.reply_text("استخدم الأزرار أو /start")
            finally:
                db.close()
    
    async def handle_funding_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if not text.isdigit():
            await update.message.reply_text("❌ أدخل رقم صحيح!")
            return
        
        requested_members = int(text)
        db = get_db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else 25
            points_needed = requested_members * points_per_member
            
            if user.points < points_needed:
                await update.message.reply_text(
                    f"❌ نقاطك غير كافية!\n"
                    f"💎 لديك: {user.points}\n"
                    f"💰 تحتاج: {points_needed}\n"
                    f"⭐ الناقص: {points_needed - user.points}"
                )
                return
            
            context.user_data['requested_members'] = requested_members
            context.user_data['points_needed'] = points_needed
            
            await update.message.reply_text(
                f"✅ الطلب مقبول!\n"
                f"📊 الأعضاء: {requested_members}\n"
                f"💰 التكلفة: {points_needed} نقطة\n\n"
                f"📝 ارسل رابط قناتك/مجموعتك:\n"
                f"(يبدأ بـ @ أو https://t.me/)"
            )
        finally:
            db.close()
    
    async def handle_channel_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        link = update.message.text
        db = get_db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user or 'requested_members' not in context.user_data:
                return
            
            channel_id = self.extract_channel_id(link)
            if not channel_id:
                await update.message.reply_text("❌ رابط غير صالح!")
                return
            
            try:
                chat_member = await context.bot.get_chat_member(channel_id, context.bot.id)
                if chat_member.status not in ['administrator', 'creator']:
                    await update.message.reply_text("❌ البوت ليس أدمن في القناة!")
                    return
            except:
                await update.message.reply_text("❌ لا يمكن الوصول للقناة!")
                return
            
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
            
            await self.notify_admins_about_request(context.bot, funding_request, user)
            
            await update.message.reply_text(
                f"✅ تم استلام طلبك!\n"
                f"📊 رقم الطلب: {funding_request.id}\n"
                f"👥 الأعضاء: {requested_members}\n"
                f"💰 النقاط المخصومة: {points_needed}\n"
                f"⭐ نقاطك المتبقية: {user.points}\n\n"
                f"⏳ بانتظار الموافقة..."
            )
            
            context.user_data.clear()
            
        finally:
            db.close()
    
    async def handle_points_transfer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        db = get_db()
        
        try:
            if not text.startswith('تحويل '):
                return
            
            parts = text.split()
            if len(parts) != 3:
                await update.message.reply_text("❌ صيغة خاطئة: تحويل [المبلغ] [إيدي المستخدم]")
                return
            
            amount = int(parts[1])
            target_user_id = int(parts[2])
            
            settings = db.query(SystemSettings).first()
            if not settings or not settings.transfer_enabled:
                await update.message.reply_text("❌ خدمة التحويل معطلة!")
                return
            
            if target_user_id == user_id:
                await update.message.reply_text("❌ لا يمكنك التحويل لنفسك!")
                return
            
            sender = db.query(User).filter_by(user_id=user_id).first()
            if not sender:
                await update.message.reply_text("❌ حسابك غير موجود!")
                return
            
            fee_percent = settings.transfer_fee_percent
            fee_amount = int(amount * fee_percent / 100)
            total_deduct = amount + fee_amount
            
            if sender.points < total_deduct:
                await update.message.reply_text(
                    f"❌ نقاطك غير كافية!\n"
                    f"💎 تحتاج: {total_deduct} نقطة\n"
                    f"⭐ لديك: {sender.points} نقطة"
                )
                return
            
            receiver = db.query(User).filter_by(user_id=target_user_id).first()
            if not receiver:
                await update.message.reply_text("❌ المستخدم غير موجود!")
                return
            
            sender.points -= total_deduct
            receiver.points += amount
            
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
            
            await update.message.reply_text(
                f"✅ تم تحويل {amount} نقطة!\n\n"
                f"📤 إلى: {receiver.first_name or 'مستخدم'} ({target_user_id})\n"
                f"💸 العمولة: {fee_amount} نقطة ({fee_percent}%)\n"
                f"💰 الإجمالي: {total_deduct} نقطة\n"
                f"⭐ رصيدك الجديد: {sender.points} نقطة"
            )
            
            try:
                await context.bot.send_message(
                    target_user_id,
                    f"🎉 استلمت تحويل نقاط!\n\n"
                    f"📥 من: {sender.first_name or 'مستخدم'} ({user_id})\n"
                    f"💰 المبلغ: {amount} نقطة\n"
                    f"⭐ رصيدك الجديد: {receiver.points} نقطة"
                )
            except:
                pass
            
        except ValueError:
            await update.message.reply_text("❌ أدخل أرقام صحيحة!")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        finally:
            db.close()
    
    async def notify_admins_about_request(self, bot, request, user):
        db = get_db()
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
    
    async def handle_admin_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        user_id = update.effective_user.id
        db = get_db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user or not user.is_admin:
                return
            
            if text.startswith('/add_admin'):
                parts = text.split()
                if len(parts) < 2:
                    await update.message.reply_text("❌ صيغة: /add_admin @username أو user_id")
                    return
                
                target = parts[1].replace('@', '')
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
            
            elif text.startswith('/ban'):
                parts = text.split()
                if len(parts) < 3:
                    await update.message.reply_text("❌ صيغة: /ban @username السبب")
                    return
                
                target = parts[1].replace('@', '')
                reason = ' '.join(parts[2:])
                
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
            
            elif text.startswith('/add_points'):
                parts = text.split()
                if len(parts) < 3:
                    await update.message.reply_text("❌ صيغة: /add_points @username العدد")
                    return
                
                target = parts[1].replace('@', '')
                points = int(parts[2])
                
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
            
            elif text.startswith('/maintenance'):
                parts = text.split()
                if len(parts) < 2:
                    await update.message.reply_text("❌ صيغة: /maintenance on/off")
                    return
                
                mode = parts[1].lower()
                settings = db.query(SystemSettings).first()
                if settings:
                    if mode == 'on':
                        settings.maintenance_mode = True
                        await update.message.reply_text("✅ تم تفعيل وضع الصيانة")
                    elif mode == 'off':
                        settings.maintenance_mode = False
                        await update.message.reply_text("✅ تم تعطيل وضع الصيانة")
                    db.commit()
            
            elif text.startswith('/set_fee'):
                parts = text.split()
                if len(parts) < 2:
                    await update.message.reply_text("❌ صيغة: /set_fee النسبة")
                    return
                
                try:
                    fee = int(parts[1])
                    if fee < 0 or fee > 50:
                        await update.message.reply_text("❌ النسبة بين 0 و 50!")
                        return
                    
                    settings = db.query(SystemSettings).first()
                    if settings:
                        old_fee = settings.transfer_fee_percent
                        settings.transfer_fee_percent = fee
                        db.commit()
                        await update.message.reply_text(f"✅ تم تغيير العمولة من {old_fee}% إلى {fee}%")
                except ValueError:
                    await update.message.reply_text("❌ أدخل رقم صحيح!")
            
            elif text.startswith('/add_support'):
                parts = text.split()
                if len(parts) < 2:
                    await update.message.reply_text("❌ صيغة: /add_support @username")
                    return
                
                target = parts[1].replace('@', '')
                
                try:
                    user_info = await context.bot.get_chat(target)
                    
                    existing = db.query(SupportContact).filter_by(user_id=user_info.id).first()
                    if existing:
                        await update.message.reply_text("⚠️ هذا المستخدم مضاف بالفعل!")
                        return
                    
                    support = SupportContact(
                        user_id=user_info.id,
                        username=user_info.username or user_info.first_name,
                        added_by=user_id,
                        added_at=datetime.now()
                    )
                    db.add(support)
                    db.commit()
                    
                    await update.message.reply_text(f"✅ تم إضافة @{user_info.username or user_info.first_name} للدعم")
                except Exception as e:
                    await update.message.reply_text(f"❌ خطأ: {str(e)}")
            
            elif text.startswith('/add_channel'):
                parts = text.split()
                if len(parts) < 3:
                    await update.message.reply_text("❌ صيغة: /add_channel @channel_id العنوان [mandatory/optional]")
                    return
                
                channel_id = parts[1]
                channel_title = ' '.join(parts[2:-1]) if len(parts) > 3 else parts[2]
                is_mandatory = parts[-1].lower() == 'mandatory' if len(parts) > 3 else False
                
                existing = db.query(Channel).filter_by(channel_id=channel_id).first()
                if existing:
                    await update.message.reply_text("⚠️ هذه القناة مضافه بالفعل!")
                    return
                
                channel = Channel(
                    channel_id=channel_id,
                    channel_title=channel_title,
                    is_mandatory=is_mandatory,
                    added_by_admin=user_id,
                    created_at=datetime.now()
                )
                db.add(channel)
                db.commit()
                
                status = "إجبارية" if is_mandatory else "اختيارية"
                await update.message.reply_text(f"✅ تم إضافة القناة {channel_title}\n📢 الحالة: {status}")
            
            elif text.startswith('/add_group'):
                parts = text.split()
                if len(parts) < 3:
                    await update.message.reply_text("❌ صيغة: /add_group @group_id العنوان")
                    return
                
                group_id = parts[1]
                group_title = ' '.join(parts[2:])
                
                existing = db.query(GroupSource).filter_by(group_id=group_id).first()
                if existing:
                    await update.message.reply_text("⚠️ هذه المجموعة مضافه بالفعل!")
                    return
                
                group = GroupSource(
                    group_id=group_id,
                    group_title=group_title,
                    added_by_admin=user_id,
                    created_at=datetime.now()
                )
                db.add(group)
                db.commit()
                
                await update.message.reply_text(f"✅ تم إضافة المجموعة {group_title}")
        
        finally:
            db.close()
    
    # ==================== 🚀 تشغيل البوت ====================
    async def run(self):
        if self.config.BOT_TOKEN == "ضع_توكن_البوت_هنا":
            print("❌ ضع توكن البوت!")
            return
        
        print("🔄 جاري تهيئة قاعدة البيانات...")
        if not init_database():
            print("❌ فشل تهيئة قاعدة البيانات!")
            return
        
        self.keep_alive.start_web_server()
        print("✅ خادم ويب يعمل")
        
        print("🤖 جاري إنشاء تطبيق البوت...")
        self.application = Application.builder().token(self.config.BOT_TOKEN).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        print("🚀 جاري تشغيل البوت...")
        print(f"👑 المدير: {self.config.ADMIN_ID}")
        
        try:
            bot_info = await self.application.bot.get_me()
            print(f"🤖 اسم البوت: @{bot_info.username}")
            
            await self.application.bot.send_message(
                Config.ADMIN_ID,
                f"🚀 البوت بدأ التشغيل!\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🤖 @{bot_info.username}\n\n"
                f"✅ النظام يعمل الآن 24/7"
            )
        except Exception as e:
            print(f"⚠️ لم يتم إرسال رسالة البداية: {e}")
        
        self.keep_alive.start_ping_scheduler(self.application.bot)
        
        print("✅ البوت يعمل الآن بنجاح!")
        print("⏰ نظام ping يعمل (كل دقيقتين)")
        
        await self.application.run_polling(allowed_updates="all")

# ==================== 📦 التشغيل الرئيسي ====================
if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    bot = TelegramBot()
    
    try:
        print("=" * 50)
        print("🤖 بوت تمويل القنوات")
        print("👑 المدير: 6130994941")
        print("⏰ يعمل 24/7")
        print("=" * 50)
        
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("\n👋 تم إيقاف البوت")
    except Exception as e:
        print(f"❌ خطأ: {e}")
        print("🔄 جاري إعادة التشغيل خلال 10 ثواني...")
        time.sleep(10)
        try:
            asyncio.run(bot.run())
        except:
            print("❌ فشل إعادة التشغيل")
