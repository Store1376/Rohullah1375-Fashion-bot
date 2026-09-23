import os
import sqlite3
import logging
import threading
from datetime import datetime

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
    "gpt-4o-mini"
).strip()


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
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


def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


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
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            phone TEXT DEFAULT '',
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
            payment_ref TEXT DEFAULT '',
            note TEXT DEFAULT '',
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
        """)

        defaults = {
            "buy_rate": "70",
            "sell_rate": "69",
            "maintenance": "0",
            "ai_enabled": "1",
            "support": "@Rohullah1375",
        }

        for key, value in defaults.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO settings(key,value)
                VALUES(?,?)
                """,
                (key, value)
            )

        conn.commit()
        conn.close()


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

    return row["value"] if row else ""


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


def log_admin(admin_id, action, detail=""):
    with db_lock:
        conn = db()

        conn.execute(
            """
            INSERT INTO admin_logs(
                admin_id,
                action,
                detail,
                created_at
            )
            VALUES(?,?,?,?)
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
# HELPERS
# =========================================================

def money(value):
    return f"{float(value):,.2f}"


def is_admin(user_id):
    return user_id in ADMIN_IDS


def ensure_user(user):
    with db_lock:
        conn = db()

        conn.execute(
            """
            INSERT INTO users(
                tg_id,
                username,
                first_name,
                created_at
            )
            VALUES(?,?,?,?)

            ON CONFLICT(tg_id)
            DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
            """,
            (
                user.id,
                user.username or "",
                user.first_name or "",
                now()
            )
        )

        conn.commit()
        conn.close()


def blocked(user_id):
    conn = db()

    row = conn.execute(
        """
        SELECT blocked
        FROM users
        WHERE tg_id=?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return bool(row["blocked"]) if row else False


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
                "💵 نرخ‌ها",
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
                "🚫 مسدود / آزاد",
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

async def notify_admins(context, text):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text
            )
        except Exception as exc:
            log.warning(
                "Admin notification failed: %s",
                exc
            )


# =========================================================
# START
# =========================================================

async def start(update, context):
    user = update.effective_user

    ensure_user(user)

    if blocked(user.id):
        await update.message.reply_text(
            "🚫 حساب شما توسط مدیریت مسدود شده است."
        )
        return

    await update.message.reply_text(
        "💰 به ربات خرید و فروش تتر خوش آمدید.\n\n"
        f"🟢 نرخ خرید: {money(setting('buy_rate'))}\n"
        f"🔴 نرخ فروش: {money(setting('sell_rate'))}\n\n"
        "لطفاً گزینه مورد نظر را انتخاب کنید:",
        reply_markup=user_menu()
    )


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_cmd(update, context):
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ دسترسی مجاز نیست."
        )
        return

    await update.message.reply_text(
        "🔐 پنل مدیریت",
        reply_markup=admin_menu()
    )


# =========================================================
# BUY / SELL
# =========================================================

async def new_order(update, context, side):
    query = update.callback_query

    await query.answer()

    if setting("maintenance") == "1":
        await query.edit_message_text(
            "🔧 ربات موقتاً در حالت تعمیرات است.",
            reply_markup=user_menu()
        )
        return

    if side == "buy":
        rate = float(setting("sell_rate"))
        title = "🟢 خرید تتر"
    else:
        rate = float(setting("buy_rate"))
        title = "🔴 فروش تتر"

    context.user_data.clear()

    context.user_data["state"] = "order_amount"
    context.user_data["side"] = side
    context.user_data["rate"] = rate

    await query.edit_message_text(
        f"{title}\n\n"
        f"💵 نرخ فعلی: {money(rate)}\n\n"
        "مقدار USDT را وارد کنید.\n"
        "مثال:\n"
        "100"
    )


async def create_order(update, context):
    try:
        amount = float(
            update.message.text
            .replace(",", "")
            .strip()
        )

        if amount <= 0:
            raise ValueError

    except ValueError:
        await update.message.reply_text(
            "❌ لطفاً مقدار معتبر وارد کنید.\n"
            "مثال: 100"
        )
        return

    side = context.user_data.get("side")
    rate = float(
        context.user_data.get("rate", 0)
    )

    if side not in ("buy", "sell") or rate <= 0:
        context.user_data.clear()

        await update.message.reply_text(
            "❌ اطلاعات سفارش منقضی شده است.",
            reply_markup=user_menu()
        )
        return

    total = amount * rate

    with db_lock:
        conn = db()

        cur = conn.execute(
            """
            INSERT INTO orders(
                tg_id,
                side,
                usdt,
                rate,
                total,
                status,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?,?)
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

        order_id = cur.lastrowid

        conn.commit()
        conn.close()

    side_text = (
        "خرید"
        if side == "buy"
        else "فروش"
    )

    context.user_data.clear()

    await update.message.reply_text(
        f"✅ سفارش #{order_id} ثبت شد.\n\n"
        f"📌 نوع: {side_text}\n"
        f"💵 مقدار: {amount:g} USDT\n"
        f"📊 نرخ: {money(rate)}\n"
        f"💰 مبلغ: {money(total)}\n\n"
        "⏳ سفارش برای مدیریت ارسال شد.",
        reply_markup=user_menu()
    )

    await notify_admins(
        context,
        "🔔 سفارش جدید\n\n"
        f"🆔 سفارش: #{order_id}\n"
        f"👤 کاربر: {update.effective_user.id}\n"
        f"📌 نوع: {side_text}\n"
        f"💵 مقدار: {amount:g} USDT\n"
        f"💰 مبلغ: {money(total)}"
    )


# =========================================================
# RATES
# =========================================================

async def rates(update, context):
    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        "📊 نرخ‌های فعلی\n\n"
        f"🟢 نرخ خرید: {money(setting('buy_rate'))}\n"
        f"🔴 نرخ فروش: {money(setting('sell_rate'))}\n\n"
        "ℹ️ نرخ‌ها توسط مدیریت تنظیم می‌شوند.",
        reply_markup=user_menu()
    )


# =========================================================
# PROFILE
# =========================================================

async def profile(update, context):
    query = update.callback_query

    await query.answer()

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE tg_id=?
        """,
        (query.from_user.id,)
    ).fetchone()

    conn.close()

    if row:
        name = row["first_name"] or "ثبت نشده"

        username = (
            "@" + row["username"]
            if row["username"]
            else "ندارد"
        )

        phone = row["phone"] or "ثبت نشده"

    else:
        name = (
            query.from_user.first_name
            or "ثبت نشده"
        )
        username = "ندارد"
        phone = "ثبت نشده"

    await query.edit_message_text(
        "👤 پروفایل\n\n"
        f"🆔 ID: {query.from_user.id}\n"
        f"👤 نام: {name}\n"
        f"📱 یوزرنیم: {username}\n"
        f"☎️ شماره: {phone}",
        reply_markup=user_menu()
    )


# =========================================================
# MY ORDERS
# =========================================================

async def myorders(update, context):
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
            "📦 سفارش‌های من\n\n"
            "هنوز سفارشی ثبت نکرده‌اید."
        )
    else:
        lines = ["📦 سفارش‌های شما:\n"]

        for row in rows:
            side = (
                "🟢 خرید"
                if row["side"] == "buy"
                else "🔴 فروش"
            )

            lines.append(
                f"#{row['id']} | {side}\n"
                f"💵 مقدار: {row['usdt']:g} USDT\n"
                f"💰 مبلغ: {row['total']:,.2f}\n"
                f"📌 وضعیت: {row['status']}\n"
                f"🕒 {row['created_at']}"
            )

        text = "\n\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=user_menu()
    )


# =========================================================
# PAYMENT
# =========================================================

async def payment(update, context):
    query = update.callback_query

    await query.answer()

    context.user_data.clear()
    context.user_data["state"] = "payment_ref"

    await query.edit_message_text(
        "💳 پرداخت / ارسال رسید\n\n"
        "شماره سفارش و TXID یا اطلاعات رسید "
        "را بفرستید.\n\n"
        "مثال:\n"
        "ORDER 25\n"
        "TXID: 123456789"
    )


async def save_payment(update, context):
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

    order_id = None

    if row:
        order_id = row["id"]

        conn.execute(
            """
            UPDATE orders
            SET
                payment_ref=?,
                payment_status=?,
                updated_at=?
            WHERE id=?
            """,
            (
                ref,
                "submitted",
                now(),
                order_id
            )
        )

        conn.commit()

    conn.close()

    context.user_data.clear()

    if order_id:
        await update.message.reply_text(
            f"✅ رسید سفارش #{order_id} ثبت شد.\n\n"
            "⏳ برای مدیریت ارسال شد.",
            reply_markup=user_menu()
        )
    else:
        await update.message.reply_text(
            "⚠️ هنوز سفارشی برای حساب شما پیدا نشد.",
            reply_markup=user_menu()
        )

    await notify_admins(
        context,
        "💳 رسید جدید\n\n"
        f"👤 کاربر: {update.effective_user.id}\n"
        f"🧾 اطلاعات:\n{ref}"
    )


# =========================================================
# SUPPORT
# =========================================================

async def support(update, context):
    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        "📞 پشتیبانی\n\n"
        f"👨‍💻 {setting('support')}",
        reply_markup=user_menu()
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

    context.user_data.clear()
    context.user_data["state"] = "ai"

    await query.edit_message_text(
        "🤖 دستیار هوشمند فعال شد.\n\n"
        "سؤال خود را بفرستید."
    )


async def ai_reply(update, context):
    if not OPENAI_API_KEY or OpenAI is None:
        await update.message.reply_text(
            "⚠️ دستیار هوشمند تنظیم نشده است.\n\n"
            "OPENAI_API_KEY را در Render وارد کنید.",
            reply_markup=user_menu()
        )

        context.user_data.clear()
        return

    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY
        )

        prompt = (
            "تو دستیار هوشمند یک ربات "
            "خرید و فروش تتر هستی.\n"
            "به زبان دری/فارسی ساده جواب بده.\n"
            "اطلاعات ساختگی درباره موجودی، "
            "پرداخت یا سفارش ایجاد نکن.\n\n"
            f"نرخ خرید: {setting('buy_rate')}\n"
            f"نرخ فروش: {setting('sell_rate')}\n\n"
            f"سؤال کاربر:\n{update.message.text}"
        )

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
            answer = "⚠️ پاسخی دریافت نشد."

        await update.message.reply_text(
            answer,
            reply_markup=user_menu()
        )

    except Exception:
        log.exception("AI error")

        await update.message.reply_text(
   
