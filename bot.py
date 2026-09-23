import os
import sqlite3
import logging
import threading
from datetime import datetime

from flask import Flask, jsonify

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# =========================================================
# CONFIG
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv(
        "ADMIN_IDS",
        os.getenv("ADMIN_ID", "")
    ).split(",")
    if x.strip().isdigit()
}

PORT = int(os.getenv("PORT", "10000"))

DB_PATH = os.getenv(
    "DB_PATH",
    "bitcoin1996.db"
)

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    ""
).strip()

OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.6-luna"
).strip()

HESABPAY_API_URL = os.getenv(
    "HESABPAY_API_URL",
    ""
).strip()

HESABPAY_API_KEY = os.getenv(
    "HESABPAY_API_KEY",
    ""
).strip()

HESABPAY_WEBHOOK_TOKEN = os.getenv(
    "HESABPAY_WEBHOOK_TOKEN",
    ""
).strip()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)

log = logging.getLogger("Bitcoin1996Bot")


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

db_lock = threading.Lock()


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    with db_lock:

        conn = db()

        conn.executescript("""
        
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone TEXT,
            blocked INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            side TEXT NOT NULL,
            usdt REAL NOT NULL,
            rate REAL NOT NULL,
            total REAL NOT NULL,
            status TEXT NOT NULL,
            payment_status TEXT DEFAULT 'pending',
            payment_ref TEXT,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            direction TEXT,
            text TEXT,
            created_at TEXT NOT NULL
        );

        """)

        defaults = {

            "buy_rate": "70",

            "sell_rate": "69",

            "maintenance": "0",

            "ai_enabled": "1",

            "support": "@Rohullah1375"

        }

        for key, value in defaults.items():

            conn.execute(
                """
                INSERT OR IGNORE INTO settings
                (key, value)
                VALUES (?, ?)
                """,
                (key, value)
            )

        conn.commit()

        conn.close()


# =========================================================
# HELPERS
# =========================================================

def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def setting(key):

    conn = db()

    row = conn.execute(
        """
        SELECT value
        FROM settings
        WHERE key=?
        """,
        (key,)
    ).fetchone()

    conn.close()

    if row:
        return row["value"]

    return ""


def set_setting(key, value):

    with db_lock:

        conn = db()

        conn.execute(
            """
            INSERT INTO settings(key,value)
            VALUES(?,?)

            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (key, str(value))
        )

        conn.commit()

        conn.close()


def money(value):

    return f"{float(value):,.2f}"


def is_admin(user_id):

    return user_id in ADMIN_IDS


def user_row(user_id):

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE tg_id=?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return row


def ensure_user(user):

    with db_lock:

        conn = db()

        exists = conn.execute(
            """
            SELECT tg_id
            FROM users
            WHERE tg_id=?
            """,
            (user.id,)
        ).fetchone()

        if not exists:

            conn.execute(
                """
                INSERT INTO users
                (
                    tg_id,
                    username,
                    first_name,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username or "",
                    user.first_name or "",
                    now()
                )
            )

        else:

            conn.execute(
                """
                UPDATE users
                SET username=?,
                    first_name=?
                WHERE tg_id=?
                """,
                (
                    user.username or "",
                    user.first_name or "",
                    user.id
                )
            )

        conn.commit()

        conn.close()


def blocked(user_id):

    row = user_row(user_id)

    if not row:
        return False

    return bool(row["blocked"])


def log_admin(
    admin_id,
    action,
    detail=""
):

    with db_lock:

        conn = db()

        conn.execute(
            """
            INSERT INTO admin_logs
            (
                admin_id,
                action,
                detail,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                admin_id,
                action,
                detail,
                now()
            )
        )

        conn.commit()

        conn.close()


# =========================================================
# USER MENU
# =========================================================

def user_menu():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🟢 خرید تتر",
                callback_data="buy"
            ),

            InlineKeyboardButton(
                "🔴 فروش تتر",
                callback_data="sell"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 نرخ‌ها",
                callback_data="rates"
            ),

            InlineKeyboardButton(
                "📦 سفارش‌های من",
                callback_data="myorders"
            )
        ],

        [
            InlineKeyboardButton(
                "💳 پرداخت / رسید",
                callback_data="payment"
            ),

            InlineKeyboardButton(
                "👤 پروفایل",
                callback_data="profile"
            )
        ],

        [
            InlineKeyboardButton(
                "🤖 دستیار هوشمند",
                callback_data="ai"
            ),

            InlineKeyboardButton(
                "📞 پشتیبانی",
                callback_data="support"
            )
        ]

    ])


# =========================================================
# ADMIN MENU
# =========================================================

def admin_menu():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📊 داشبورد",
                callback_data="adm_dashboard"
            ),

            InlineKeyboardButton(
                "📦 سفارش‌ها",
                callback_data="adm_orders"
            )
        ],

        [
            InlineKeyboardButton(
                "👥 مشتریان",
                callback_data="adm_users"
            ),

            InlineKeyboardButton(
                "💵 نرخ خرید/فروش",
                callback_data="adm_rates"
            )
        ],

        [
            InlineKeyboardButton(
                "💳 پرداخت‌ها",
                callback_data="adm_payments"
            ),

            InlineKeyboardButton(
                "📈 گزارش‌ها",
                callback_data="adm_reports"
            )
        ],

        [
            InlineKeyboardButton(
                "📢 پیام همگانی",
                callback_data="adm_broadcast"
            ),

            InlineKeyboardButton(
                "🚫 مسدود/آزاد",
                callback_data="adm_block"
            )
        ],

        [
            InlineKeyboardButton(
                "⚙️ تنظیمات",
                callback_data="adm_settings"
            ),

            InlineKeyboardButton(
                "🔐 لاگ امنیتی",
                callback_data="adm_logs"
            )
        ]

    ])


# =========================================================
# ADMIN NOTIFICATION
# =========================================================

async def notify_admins(
    context,
    text
):

    for admin_id in ADMIN_IDS:

        try:

            await context.bot.send_message(
                chat_id=admin_id,
                text=text
            )

        except Exception as e:

            log.warning(
                "Admin notification failed: %s",
                e
            )


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    ensure_user(user)

    if blocked(user.id):

        await update.message.reply_text(
            "🚫 حساب شما توسط مدیریت مسدود شده است."
        )

        return

    buy_rate = money(
        setting("buy_rate")
    )

    sell_rate = money(
        setting("sell_rate")
    )

    await update.message.reply_text(

        "💰 به ربات خرید و فروش تتر خوش آمدید.\n\n"

        f"🟢 نرخ خرید: {buy_rate}\n"
        f"🔴 نرخ فروش: {sell_rate}\n\n"

        "لطفاً گزینه مورد نظر را انتخاب کنید:",

        reply_markup=user_menu()

    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user_id = update.effective_user.id

    if not is_admin(user_id):

        await update.message.reply_text(
            "⛔ دسترسی مجاز نیست."
        )

        return

    await update.message.reply_text(
        "🔐 پنل مدیریت\n\n"
        "از منوی زیر بخش مورد نظر را انتخاب کنید:",
        reply_markup=admin_menu()
    )


# =========================================================
# RATES
# =========================================================

async def rates(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    buy_rate = money(
        setting("buy_rate")
    )

    sell_rate = money(
        setting("sell_rate")
    )

    await query.edit_message_text(

        "📊 نرخ‌های فعلی\n\n"

        f"🟢 خرید از مشتری: {buy_rate}\n"
        f"🔴 فروش به مشتری: {sell_rate}",

        reply_markup=user_menu()
    )


# =========================================================
# PROFILE
# =========================================================

async def profile(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    row = user_row(
        query.from_user.id
    )

    username = (
        f"@{row['username']}"
        if row and row["username"]
        else "ندارد"
    )

    first_name = (
        row["first_name"]
        if row
        else query.from_user.first_name
    )

    phone = (
        row["phone"]
        if row and row["phone"]
        else "ثبت نشده"
    )

    text = (
        "👤 پروفایل شما\n\n"

        f"🆔 ID: {query.from_user.id}\n"
        f"👤 نام: {first_name}\n"
        f"📱 یوزرنیم: {username}\n"
        f"☎️ شماره: {phone}"
    )

    await query.edit_message_text(
        text,
        reply_markup=user_menu()
    )


# =========================================================
# MY ORDERS
# =========================================================

async def myorders(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE tg_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (query.from_user.id,)
    ).fetchall()

    conn.close()

    if not rows:

        text = (
            "📦 شما هنوز سفارشی ثبت نکرده‌اید."
        )

    else:

        lines = [
            "📦 آخرین سفارش‌های شما:\n"
        ]

        for row in rows:

            side = (
                "خرید"
                if row["side"] == "buy"
                else "فروش"
            )

            lines.append(
                f"#{row['id']} | "
                f"{side} | "
                f"{row['usdt']:g} USDT | "
                f"{row['total']:,.2f} | "
                f"{row['status']}"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=user_menu()
    )


# =========================================================
# NEW ORDER
# =========================================================

async def new_order(
    update,
    context,
    side
):

    query = update.callback_query

    await query.answer()

    if side == "buy":

        rate = float(
            setting("sell_rate")
        )

        title = "🟢 خرید تتر"

    else:

        rate = float(
            setting("buy_rate")
        )

        title = "🔴 فروش تتر"

    context.user_data["state"] = (
        "order_amount"
    )

    context.user_data["side"] = side

    context.user_data["rate"] = rate

    await query.edit_message_text(

        f"{title}\n\n"

        f"💵 نرخ محاسبه: {money(rate)}\n\n"

        "مقدار USDT مورد نظر را "
        "فقط به صورت عدد بفرستید.\n\n"

        "مثال:\n"
        "100"

    )


# =========================================================
# CREATE ORDER
# =========================================================

async def create_order_from_amount(
    update,
    context
):

    try:

        amount = float(
            update.message.text
            .replace(",", "")
            .strip()
        )

        if amount <= 0:
            raise ValueError

    except Exception:

        await update.message.reply_text(
            "❌ لطفاً مقدار معتبر وارد کنید."
        )

        return

    side = context.user_data.get(
        "side"
    )

    rate = float(
        context.user_data.get(
            "rate",
            0
        )
    )

    total = amount * rate

    with db_lock:

        conn = db()

        conn.execute(
            """
            INSERT INTO orders
            (
                tg_id,
                side,
                usdt,
                rate,
                total,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                update.effective_user.id,
                side,
                amount,
                rate,
                total,
                "در انتظار تایید",
                now(),
                now()
            )
        )

        order_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        conn.commit()

        conn.close()

    context.user_data.clear()

    side_text = (
        "خرید"
        if side == "buy"
        else "فروش"
    )

    await update.message.reply_text(

        f"✅ سفارش #{order_id} ثبت شد.\n\n"

        f"نوع: {side_text}\n"
        f"مقدار: {amount:g} USDT\n"
        f"نرخ: {money(rate)}\n"
        f"مبلغ: {money(total)}\n\n"

        "⏳ سفارش شما برای مدیریت ارسال شد.",

        reply_markup=user_menu()
    )

    await notify_admins(

        context,

        "🔔 سفارش جدید\n\n"
        f"شماره: #{order_id}\n"
        f"کاربر: {update.effective_user.id}\n"
        f"نوع: {side_text}\n"
        f"مقدار: {amount:g} USDT\n"
        f"مبلغ: {money(total)}"

    )# =========================================================
# PAYMENT
# =========================================================

async def payment(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data["state"] = "payment_ref"

    await query.edit_message_text(
        "💳 پرداخت / ارسال رسید\n\n"
        "شناسه سفارش و در صورت وجود TXID یا شماره رسید "
        "را در یک پیام بفرستید.\n\n"
        "مثال:\n"
        "ORDER 25\n"
        "TXID: 123456",
    )


async def save_payment_ref(update, context):

    ref = update.message.text.strip()

    conn = db()

    row = conn.execute(
        """
        SELECT id
        FROM orders
        WHERE tg_id=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (update.effective_user.id,)
    ).fetchone()

    if row:

        conn.execute(
            """
            UPDATE orders
            SET payment_ref=?,
                payment_status='submitted',
                updated_at=?
            WHERE id=?
            """,
            (
                ref,
                now(),
                row["id"]
            )
        )

    conn.commit()
    conn.close()

    context.user_data.clear()

    await update.message.reply_text(
        "✅ رسید پرداخت ثبت شد.\n\n"
        "رسید برای مدیریت ارسال گردید.",
        reply_markup=user_menu()
    )

    await notify_admins(
        context,
        "💳 رسید جدید\n\n"
        f"کاربر: {update.effective_user.id}\n"
        f"رسید: {ref}"
    )


# =========================================================
# AI
# =========================================================

async def ai(update, context):

    query = update.callback_query
    await query.answer()

    if setting("ai_enabled") != "1":

        await query.edit_message_text(
            "🤖 دستیار هوشمند فعلاً خاموش است.",
            reply_markup=user_menu()
        )

        return

    context.user_data["state"] = "ai"

    await query.edit_message_text(
        "🤖 دستیار هوشمند فعال شد.\n\n"
        "سوال خود را بفرستید."
    )


async def ai_reply(update, context):

    if not OPENAI_API_KEY:

        await update.message.reply_text(
            "⚠️ کلید OPENAI_API_KEY تنظیم نشده است.\n\n"
            "آن را در Environment Variables گیت‌هاب/Render وارد کنید."
        )

        return

    if OpenAI is None:

        await update.message.reply_text(
            "⚠️ کتابخانه OpenAI نصب نشده است."
        )

        return

    try:

        client = OpenAI(
            api_key=OPENAI_API_KEY
        )

        prompt = f"""
تو دستیار هوشمند یک ربات خرید و فروش تتر هستی.

زبان پاسخ: دری/فارسی.

نرخ فعلی خرید:
{setting("buy_rate")}

نرخ فعلی فروش:
{setting("sell_rate")}

قوانین:
- نرخ یا موجودی ساختگی ایجاد نکن.
- درباره سفارش‌ها فقط اطلاعاتی بده که واقعاً در سیستم وجود دارد.
- اگر سوال مربوط به انجام معامله است، کاربر را به منوی ربات راهنمایی کن.
- پاسخ‌ها کوتاه، واضح و دوستانه باشند.

سوال کاربر:
{update.message.text}
"""

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=prompt
        )

        answer = getattr(
            response,
            "output_text",
            None
        )

        if not answer:
            answer = "متأسفانه پاسخ دریافت نشد."

        await update.message.reply_text(
            answer,
            reply_markup=user_menu()
        )

    except Exception as e:

        log.exception(
            "AI error: %s",
            e
        )

        await update.message.reply_text(
            "⚠️ دستیار هوشمند فعلاً پاسخ نمی‌دهد.\n"
            "لطفاً کمی بعد دوباره امتحان کنید."
        )

    context.user_data.clear()


# =========================================================
# SUPPORT
# =========================================================

async def support(update, context):

    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📞 پشتیبانی\n\n"
        f"برای تماس با مدیریت:\n"
        f"{setting('support')}",
        reply_markup=user_menu()
    )


# =========================================================
# ADMIN STATISTICS
# =========================================================

def admin_stats():

    conn = db()

    users = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM users
        """
    ).fetchone()["n"]

    orders = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM orders
        """
    ).fetchone()["n"]

    pending = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM orders
        WHERE status='در انتظار تایید'
        """
    ).fetchone()["n"]

    volume = conn.execute(
        """
        SELECT COALESCE(SUM(total),0) AS n
        FROM orders
        WHERE status NOT IN ('رد شد','لغو شد')
        """
    ).fetchone()["n"]

    conn.close()

    return users, orders, pending, volume


# =========================================================
# ADMIN DASHBOARD
# =========================================================

async def admin_dashboard(update, context):

    query = update.callback_query
    await query.answer()

    users, orders, pending, volume = admin_stats()

    await query.edit_message_text(

        "📊 داشبورد مدیریت\n\n"

        f"👥 مشتریان: {users}\n"
        f"📦 کل سفارش‌ها: {orders}\n"
        f"⏳ سفارش‌های در انتظار: {pending}\n"
        f"💰 حجم معاملات ثبت‌شده: {volume:,.2f}\n\n"

        f"🟢 نرخ خرید: {setting('buy_rate')}\n"
        f"🔴 نرخ فروش: {setting('sell_rate')}",

        reply_markup=admin_menu()
    )


# =========================================================
# ADMIN ORDERS
# =========================================================

async def admin_orders(update, context):

    query = update.callback_query
    await query.answer()

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    conn.close()

    if not rows:

        text = "📦 هیچ سفارشی وجود ندارد."

    else:

        lines = [
            "📦 سفارش‌های اخیر:\n"
        ]

        for row in rows:

            side = (
                "🟢 خرید"
                if row["side"] == "buy"
                else "🔴 فروش"
            )

            lines.append(
                f"#{row['id']} | "
                f"{row['tg_id']} | "
                f"{side} | "
                f"{row['usdt']:g} USDT | "
                f"{row['total']:,.2f}\n"
                f"وضعیت: {row['status']}"
            )

        text = "\n\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔄 بروزرسانی",
                    callback_data="adm_orders"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ مدیریت",
                    callback_data="adm_back"
                )
            ]
        ])
    )


# =========================================================
# ADMIN USERS
# =========================================================

async def admin_users(update, context):

    query = update.callback_query
    await query.answer()

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT 30
        """
    ).fetchall()

    conn.close()

    if not rows:

        text = "👥 هنوز مشتری‌ای ثبت نشده است."

    else:

        lines = [
            "👥 مشتریان:\n"
        ]

        for row in rows:

            status = (
                "🚫 مسدود"
                if row["blocked"]
                else "✅ فعال"
            )

            username = (
                "@" + row["username"]
                if row["username"]
                else "-"
            )

            lines.append(
                f"🆔 {row['tg_id']}\n"
                f"👤 {row['first_name']}\n"
                f"📱 {username}\n"
                f"وضعیت: {status}"
            )

        text = "\n\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚫 مسدود / آزاد",
                    callback_data="adm_block"
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ مدیریت",
                    callback_data="adm_back"
                )
            ]
        ])
    )


# =========================================================
# ADMIN RATE MANAGEMENT
# =========================================================

async def admin_rates(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data["admin_state"] = "rates"

    await query.edit_message_text(

        "💵 مدیریت نرخ‌ها\n\n"

        f"🟢 نرخ خرید فعلی: {setting('buy_rate')}\n"
        f"🔴 نرخ فروش فعلی: {setting('sell_rate')}\n\n"

        "برای تغییر این قالب را بفرستید:\n\n"

        "خرید 70\n"
        "فروش 71\n\n"

        "یا:\n"
        "buy 70\n"
        "sell 71"
    )


# =========================================================
# ADMIN PAYMENTS
# =========================================================

async def admin_payments(update, context):

    query = update.callback_query
    await query.answer()

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE payment_ref IS NOT NULL
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    conn.close()

    if not rows:

        text = (
            "💳 هنوز رسید پرداختی ثبت نشده است."
        )

    else:

        lines = [
            "💳 پرداخت‌ها:\n"
        ]

        for row in rows:

            lines.append(
                f"#{row['id']} | "
                f"کاربر {row['tg_id']}\n"
                f"وضعیت: {row['payment_status']}\n"
                f"رسید: {row['payment_ref']}"
            )

        text = "\n\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


# =========================================================
# ADMIN REPORTS
# =========================================================

async def admin_reports(update, context):

    query = update.callback_query
    await query.answer()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    month = datetime.now().strftime(
        "%Y-%m"
    )

    conn = db()

    daily = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            COALESCE(SUM(total),0) AS s
        FROM orders
        WHERE substr(created_at,1,10)=?
        """,
        (today,)
    ).fetchone()

    monthly = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            COALESCE(SUM(total),0) AS s
        FROM orders
        WHERE substr(created_at,1,7)=?
        """,
        (month,)
    ).fetchone()

    total = conn.execute(
        """
        SELECT
            COUNT(*) AS n,
            COALESCE(SUM(total),0) AS s
        FROM orders
        """
    ).fetchone()

    conn.close()

    text = (
        "📈 گزارش معاملات\n\n"

        f"📅 امروز:\n"
        f"سفارش: {daily['n']}\n"
        f"مبلغ: {daily['s']:,.2f}\n\n"

        f"📅 این ماه:\n"
        f"سفارش: {monthly['n']}\n"
        f"مبلغ: {monthly['s']:,.2f}\n\n"

        f"📊 کل:\n"
        f"سفارش: {total['n']}\n"
        f"مبلغ: {total['s']:,.2f}"
    )

    await query.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


# =========================================================
# ADMIN BROADCAST
# =========================================================

async def admin_broadcast(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data[
        "admin_state"
    ] = "broadcast"

    await query.edit_message_text(
        "📢 پیام همگانی\n\n"
        "متن پیام را بفرستید.\n\n"
        "پیام برای تمام کاربران فعال ارسال می‌شود."
    )


# =========================================================
# ADMIN BLOCK / UNBLOCK
# =========================================================

async def admin_block(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data[
        "admin_state"
    ] = "block"

    await query.edit_message_text(
        "🚫 مسدود / آزاد کردن کاربر\n\n"
        "ID عددی کاربر را ارسال کنید."
    )


# =========================================================
# ADMIN SETTINGS
# =========================================================

async def admin_settings(update, context):

    query = update.callback_query
    await query.answer()

    maintenance = (
        "روشن"
        if setting("maintenance") == "1"
        else "خاموش"
    )

    ai_status = (
        "روشن"
        if setting("ai_enabled") == "1"
        else "خاموش"
    )

    await query.edit_message_text(

        "⚙️ تنظیمات ربات\n\n"

        f"🤖 دستیار هوشمند: {ai_status}\n"
        f"🔧 حالت تعمیرات: {maintenance}\n"
        f"📞 پشتیبانی: {setting('support')}\n\n"

        "دستورات قابل استفاده مدیر:\n\n"

        "ai on\n"
        "ai off\n\n"

        "maintenance on\n"
        "maintenance off",

        reply_markup=admin_menu()
    )


# =========================================================
# ADMIN SECURITY LOGS
# =========================================================

async def admin_logs(update, context):

    query = update.callback_query
    await query.answer()

    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM admin_logs
        ORDER BY id DESC
        LIMIT 25
        """
    ).fetchall()

    conn.close()

    if not rows:

        text = "🔐 هنوز لاگی ثبت نشده است."

    else:

        lines = [
            "🔐 آخرین فعالیت‌های مدیریتی:\n"
        ]

        for row in rows:

            lines.append(
                f"{row['created_at']}\n"
                f"مدیر: {row['admin_id']}\n"
                f"عملیات: {row['action']}\n"
                f"جزئیات: {row['detail']}"
            )

        text = "\n\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


# =========================================================
# CALLBACK HANDLER
# =========================================================

async def callbacks(update, context):

    query = update.callback_query

    data = query.data

    if data == "buy":
        return await new_order(
            update,
            context,
            "buy"
        )

    if data == "sell":
        return await new_order(
            update,
            context,
            "sell"
        )

    if data == "rates":
        return await rates(
            update,
            context
        )

    if data == "profile":
        return await profile(
            update,
            context
        )

    if data == "myorders":
        return await myorders(
            update,
            context
        )

    if data == "payment":
        return await payment(
            update,
            context
        )

    if data == "ai":
        return await ai(
            update,
            context
        )

    if data == "support":
        return await support(
            update,
            context
        )

    # -----------------------------
    # ADMIN
    # -----------------------------

    if not is_admin(
        query.from_user.id
    ):

        await query.answer(
            "⛔ دسترسی مجاز نیست.",
            show_alert=True
        )

        return

    if data == "adm_dashboard":

        return await admin_dashboard(
            update,
            context
        )

    if data == "adm_orders":

        return await admin_orders(
            update,
            context
        )

    if data == "adm_users":

        return await admin_users(
            update,
            context
        )

    if data == "adm_rates":

        return await admin_rates(
            update,
            context
        )

    if data == "adm_payments":

        return await admin_payments(
            update,
            context
        )

    if data == "adm_reports":

        return await admin_reports(
            update,
            context
        )

    if data == "adm_broadcast":

        return await admin_broadcast(
            update,
            context
        )

    if data == "adm_block":

        return await admin_block(
            update,
            context
        )

    if data == "adm_settings":

        return await admin_settings(
            update,
            context
        )

    if data == "adm_logs":

        return await admin_logs(
            update,
            context
        )

    if data == "adm_back":

        await query.answer()

        await query.edit_message_text(
            "🔐 پنل مدیریت",
            reply_markup=admin_menu()
        )

        return


# =========================================================
# TEXT HANDLER
# =========================================================

async def text_handler(
    update,
    context
):

    user = update.effective_user

    ensure_user(user)

    if blocked(user.id):

        await update.message.reply_text(
            "🚫 حساب شما مسدود است."
        )

        return

    state = context.user_data.get(
        "state"
    )

    # -----------------------------
    # USER ORDER
    # -----------------------------

    if state == "order_amount":

        return await create_order_from_amount(
            update,
            context
        )

    # -----------------------------
    # PAYMENT
    # -----------------------------

    if state == "payment_ref":

        return await save_payment_ref(
            update,
            context
        )

    # -----------------------------
    # AI
    # -----------------------------

    if state == "ai":

        return await ai_reply(
            update,
            context
        )

    # -----------------------------
    # ADMIN
    # -----------------------------

    if is_admin(user.id):

        admin_state = context.user_data.get(
            "admin_state"
        )

        text = update.message.text.strip()

        # -------------------------
        # RATE CHANGE
        # -------------------------

        if admin_state == "rates":

            changed = []

            for line in text.splitlines():

                parts = line.split()

                if len(parts) != 2:
                    continue

                name = parts[0].lower()

                try:

                    value = float(
                        parts[1]
                    )

                except ValueError:

                    continue

                if name in (
                    "خرید",
                    "buy"
                ):

                    set_setting(
                        "buy_rate",
                        value
                    )

                    changed.append(
                        f"🟢 خرید = {value}"
                    )

                elif name in (
                    "فروش",
                    "sell"
                ):

                    set_setting(
                        "sell_rate",
                        value
                    )

                    changed.append(
                        f"🔴 فروش = {value}"
                    )

            context.user_data.pop(
                "admin_state",
                None
            )

            log_admin(
                user.id,
                "rate_change",
                " | ".join(changed)
            )

            if changed:

                await update.message.reply_text(
                    "✅ نرخ‌ها بروزرسانی شد.\n\n"
                    + "\n".join(changed),
                    reply_markup=admin_menu()
                )

            else
