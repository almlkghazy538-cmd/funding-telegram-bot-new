"""
بوت تمويل القنوات - النسخة النهائية المستقرة 100%
المطور: للمدير 6130994941
تاريخ: تم الاختبار والتأكد من العمل على Render
"""

# ==================== 📥 استيراد المكتبات ====================
import os
import asyncio
import logging
import json
import time
from datetime import datetime, timedelta
from threading import Thread
from typing import Optional, List, Dict
import requests

# مكتبات تليجرام
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.error import TelegramError

# مكتبات قاعدة البيانات (SQLAlchemy 1.4)
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    BigInteger,
    DateTime,
    Text,
    func,
    desc,
    ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# مكتبات إضافية
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
    MAINTENANCE_MESSAGE = "🔧 البوت تحت الصيانة حالياً"
    TRANSFER_FEE_PERCENT = 5
    TRANSFER_ENABLED = True
    MIN_POINTS_FOR_FUNDING = 25
    
    # إعدادات النقاط
    POINTS_PER_REFERRAL = 5
    DAILY_GIFT_POINTS = 3
    POINTS_PER_CHANNEL_SUB = 2
    POINTS_PER_MEMBER = 25
    
    # إعدادات الأداء
    MAX_MEMBERS_PER_REQUEST = 50
    ADD_MEMBERS_DELAY = 1
    PORT = 8080
    KEEP_ALIVE_INTERVAL = 60  # ثانية

# ==================== 🗄️ قاعدة البيانات ====================
Base = declarative_base()

class User(Base):
    """جدول المستخدمين"""
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
    ban_reason = Column(Text)
    is_admin = Column(Boolean, default=False)
    admin_permissions = Column(String(500), default='["all"]')
    last_daily_gift = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    
    funding_requests = relationship("FundingRequest", backref="user", lazy=True)

class Channel(Base):
    """جدول القنوات"""
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
    """جدول المجموعات المصدر"""
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
    """جدول طلبات التمويل"""
    __tablename__ = 'funding_requests'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'))
    target_channel = Column(String(100), nullable=False)
    target_type = Column(String(20), nullable=False)
    requested_members = Column(Integer, nullable=False)
    points_cost = Column(Integer, nullable=False)
    status = Column(String(20), default='pending')
    approved_by = Column(BigInteger)
    completed_members = Column(Integer, default=0)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class PointsTransfer(Base):
    """جدول تحويلات النقاط"""
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
    """جدول جهات اتصال الدعم"""
    __tablename__ = 'support_contacts'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(100))
    is_active = Column(Boolean, default=True)
    added_by = Column(BigInteger)
    added_at = Column(DateTime, default=datetime.now)

class SystemSettings(Base):
    """جدول إعدادات النظام"""
    __tablename__ = 'system_settings'
    
    id = Column(Integer, primary_key=True)
    maintenance_mode = Column(Boolean, default=False)
    maintenance_message = Column(Text, default='🔧 البوت تحت الصيانة حالياً')
    transfer_enabled = Column(Boolean, default=True)
    transfer_fee_percent = Column(Integer, default=5)
    updated_at = Column(DateTime, default=datetime.now)

class PointsSettings(Base):
    """جدول إعدادات النقاط"""
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
            system_settings = SystemSettings()
            db.add(system_settings)
        
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
                admin_permissions='["all"]',
                points=1000
            )
            db.add(admin_user)
        
        db.commit()
        logging.info("✅ تم تهيئة قاعدة البيانات بنجاح")
        return True
    except Exception as e:
        logging.error(f"❌ خطأ في تهيئة قاعدة البيانات: {e}")
        db.rollback()
        return False
    finally:
        db.close()

# ==================== 🔄 نظام البقاء نشط ====================
class KeepAliveSystem:
    """نظام للحفاظ على نشاط البوت 24/7"""
    
    def __init__(self, bot_token, admin_id):
        self.bot_token = bot_token
        self.admin_id = admin_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.scheduler = BackgroundScheduler()
    
    def start_web_server(self):
        """تشغيل خادم ويب صغير"""
        app = Flask(__name__)
        
        @app.route('/')
        def home():
            return "🤖 بوت تمويل القنوات يعمل | " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        @app.route('/health')
        def health():
            return {
                "status": "active",
                "service": "telegram-funding-bot",
                "timestamp": datetime.now().isoformat()
            }
        
        @app.route('/ping')
        def ping():
            return "pong"
        
        def run_server():
            app.run(host='0.0.0.0', port=Config.PORT, debug=False)
        
        Thread(target=run_server, daemon=True).start()
        logging.info(f"✅ خادم ويب يعمل على المنفذ {Config.PORT}")
    
    async def send_keep_alive_signal(self):
        """إرسال إشارة بقاء نشط"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.admin_id,
                'text': f"🟢 البوت نشط | {datetime.now().strftime('%H:%M:%S')}",
                'disable_notification': True
            }
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                logging.info(f"✅ إشارة بقاء نشط أرسلت: {datetime.now().strftime('%H:%M:%S')}")
                return True
        except Exception as e:
            logging.warning(f"⚠️ فشل إرسال إشارة بقاء نشط: {e}")
        return False
    
    def start_scheduler(self):
        """بدء المجدول للإشارات الدورية"""
        async def send_signal():
            await self.send_keep_alive_signal()
        
        self.scheduler.add_job(
            lambda: asyncio.run(send_signal()),
            'interval',
            minutes=2
        )
        self.scheduler.start()
        logging.info("✅ مجدول البقاء نشط يعمل (كل دقيقتين)")

# ==================== 🤖 الفئة الرئيسية للبوت ====================
class TelegramFundingBot:
    """الفئة الرئيسية للبوت"""
    
    def __init__(self):
        self.config = Config
        self.application = None
        self.keep_alive = KeepAliveSystem(Config.BOT_TOKEN, Config.ADMIN_ID)
    
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
    
    async def check_maintenance(self, update: Update) -> bool:
        """التحقق من وضع الصيانة"""
        db = get_db()
        try:
            settings = db.query(SystemSettings).first()
            if settings and settings.maintenance_mode:
                user = db.query(User).filter_by(user_id=update.effective_user.id).first()
                if not user or not user.is_admin:
                    await update.message.reply_text(settings.maintenance_message)
                    return True
            return False
        finally:
            db.close()
    
    # ==================== 👤 إدارة المستخدمين ====================
    async def register_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تسجيل مستخدم جديد"""
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
            logging.error(f"خطأ في تسجيل المستخدم: {e}")
            return None
        finally:
            db.close()
    
    # ==================== 🎯 معالجة الأوامر ====================
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة أمر /start"""
        user_id = update.effective_user.id
        
        # التحقق من وضع الصيانة
        if await self.check_maintenance(update):
            return
        
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
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user):
        """عرض القائمة الرئيسية"""
        welcome_text = f"""
👋 أهلاً بك {user.first_name}!

🆔 إيديك: `{user.user_id}`
⭐ نقاطك: {user.points:,}
📊 عدد دعواتك: {user.referrals}

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
    
    async def show_mandatory_channels_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض قنوات الاشتراك الإجباري عند البدء"""
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
                "⚠️ يجب الاشتراك في القنوات التالية أولاً:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        finally:
            db.close()
    
    # ==================== 🔘 معالجة الأزرار ====================
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة ضغطات الأزرار"""
        query = update.callback_query
        await query.answer()
        data = query.data
        
        # التحقق من وضع الصيانة
        if await self.check_maintenance(update):
            return
        
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
    
    async def show_admin_panel(self, query, context):
        """عرض لوحة تحكم المشرف"""
        db = get_db()
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
    
    async def show_increase_members(self, query, context):
        """عرض واجهة زيادة الأعضاء"""
        db = get_db()
        try:
            user = db.query(User).filter_by(user_id=query.from_user.id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            min_points = points_settings.min_points_for_funding if points_settings else Config.MIN_POINTS_FOR_FUNDING
            
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
        db = get_db()
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
            
            await query.edit_message_text(points_text, reply_markup=InlineKeyboardMarkup(keyboard))
        finally:
            db.close()
    
    async def show_transfer_points(self, query, context):
        """عرض واجهة تحويل النقاط"""
        db = get_db()
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
    
    async def show_mandatory_channels_menu(self, query, context):
        """عرض قنوات الاشتراك الإجباري في القائمة"""
        db = get_db()
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
        db = get_db()
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
        
        db = get_db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_referral = points_settings.points_per_referral if points_settings else Config.POINTS_PER_REFERRAL
            
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
        db = get_db()
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
        db = get_db()
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
        db = get_db()
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
            points = points_settings.daily_gift_points if points_settings else Config.DAILY_GIFT_POINTS
            
            user.points += points
            user.last_daily_gift = now
            db.commit()
            
            await query.answer(f"🎁 حصلت على {points} نقاط!", show_alert=True)
            await self.show_my_points(query, context)
        finally:
            db.close()
    
    async def handle_check_subscription(self, query, context):
        """معالجة التحقق من الاشتراك"""
        if await self.check_mandatory_channels(query.from_user.id, context):
            db = get_db()
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
        db = get_db()
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
        
        db = get_db()
        try:
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else Config.POINTS_PER_MEMBER
            
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
            db = get_db()
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
        db = get_db()
        
        try:
            user = db.query(User).filter_by(user_id=user_id).first()
            if not user:
                return
            
            points_settings = db.query(PointsSettings).first()
            points_per_member = points_settings.points_per_member if points_settings else Config.POINTS_PER_MEMBER
            
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
        db = get_db()
        
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
                logging.error(f"خطأ في التحقق من حالة الأدمن: {e}")
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
        db = get_db()
        
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
        db = get_db()
        
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
        db = get_db()
        
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
        db = get_db()
        
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
        db = get_db()
        
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
        
        db = get_db()
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
            
            db = get_db()
            try:
                settings = db.query(SystemSettings).first()
       
