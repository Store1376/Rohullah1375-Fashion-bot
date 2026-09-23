import os
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)

log = logging.getLogger("Bitcoin1996Bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv(
        "ADMIN_IDS",
        os.getenv("ADMIN_ID", "")
    ).split(",")
    if x.strip().isdigit()
}

DB_PATH = os.getenv(
    "DB_PATH",
    "bitcoin1996.db"
)

PORT = int(
    os.getenv("PORT", "10000")
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

app = Flask(__name__)

db_lock = threading.Lock()


def db():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    with db_lock:

        c = db()

        c.executescript("""

        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users(
            tg_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone TEXT,
            blocked INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders(
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

        CREATE TABLE IF NOT EXISTS admin_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            detail TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages(
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

        for k, v in defaults.items():

            c.execute(
                """
                INSERT OR IGNORE INTO settings(key,value)
                VALUES(?,?)
                """,
                (k, v)
            )

        c.commit()
        c.close()


def now():

    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def setting(key):

    c = db()

    r = c.execute(
        """
        SELECT value
        FROM settings
        WHERE key=?
        """,
        (key,)
    ).fetchone()

    c.close()

    return r["value"] if r else ""


def set_setting(key, value):

    with db_lock:

        c = db()

        c.execute(
            """
            INSERT INTO settings(key,value)
            VALUES(?,?)

            ON CONFLICT(key)
            DO UPDATE SET value=excluded.value
            """,
            (key, str(value))
        )

        c.commit()
        c.close()


def log_admin(
    admin_id,
    action,
    detail=""
):

    with db_lock:

        c = db()

        c.execute(
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

        c.commit()
        c.close()


def is_admin(uid):

    return uid in ADMIN_IDS


def user_row(uid):

    c = db()

    r = c.execute(
        """
        SELECT *
        FROM users
        WHERE tg_id=?
        """,
        (uid,)
    ).fetchone()

    c.close()

    return r


def ensure_user(tg_user):

    with db_lock:

        c = db()

        r = c.execute(
            """
            SELECT tg_id
            FROM users
            WHERE tg_id=?
            """,
            (tg_user.id,)
        ).fetchone()

        if not r:

            c.execute(
                """
                INSERT INTO users(
                    tg_id,
                    username,
                    first_name,
                    created_at
                )
                VALUES(?,?,?,?)
                """,
                (
                    tg_user.id,
                    tg_user.username or "",
                    tg_user.first_name or "",
                    now()
                )
            )

        else:

            c.execute(
                """
                UPDATE users
                SET username=?,
                    first_name=?
                WHERE tg_id=?
                """,
                (
                    tg_user.username or "",
                    tg_user.first_name or "",
                    tg_user.id
                )
            )

        c.commit()
        c.close()


def blocked(uid):

    r = user_row(uid)

    return bool(
        r and r["blocked"]
    )


def money(x):

    return f"{x:,.2f}"


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


async def notify_admins(
    context,
    text
):

    for aid in ADMIN_IDS:

        try:

            await context.bot.send_message(
                aid,
                text
            )

        except Exception as e:

            log.warning(
                "admin notification failed: %s",
                e
            )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    u = update.effective_user

    ensure_user(u)

    if blocked(u.id):

        await update.message.reply_text(
            "حساب شما توسط مدیریت مسدود شده است."
        )

        return

    await update.message.reply_text(

        "💰 به ربات خرید و فروش تتر خوش آمدید.\n\n"

        f"نرخ خرید: "
        f"{money(float(setting('buy_rate')))}\n"

        f"نرخ فروش: "
        f"{money(float(setting('sell_rate')))}",

        reply_markup=user_menu()
    )


async def admin_cmd(
    update,
    context
):

    if not is_admin(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "دسترسی مجاز نیست."
        )

        return

    await update.message.reply_text(
        "🔐 پنل مدیریت",
        reply_markup=admin_menu()
    )


async def rates(
    update,
    context
):

    await update.callback_query.answer()

    await update.callback_query.edit_message_text(

        f"📊 نرخ فعلی\n\n"

        f"🟢 خرید از مشتری: "
        f"{money(float(setting('buy_rate')))}\n"

        f"🔴 فروش به مشتری: "
        f"{money(float(setting('sell_rate')))}",

        reply_markup=user_menu()
    )


async def profile(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    r = user_row(
        q.from_user.id
    )

    await q.edit_message_text(

        f"👤 پروفایل\n\n"

        f"ID: {q.from_user.id}\n"

        f"نام: "
        f"{r['first_name'] if r else ''}\n"

        f"یوزرنیم: "
        f"@{r['username'] if r and r['username'] else 'ندارد'}\n"

        f"شماره: "
        f"{r['phone'] if r and r['phone'] else 'ثبت نشده'}",

        reply_markup=user_menu()
    )


async def myorders(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM orders
        WHERE tg_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (q.from_user.id,)
    ).fetchall()

    c.close()

    if not rows:

        text = "📦 هنوز سفارشی ثبت نکرده‌اید."

    else:

        text = (
            "📦 آخرین سفارش‌ها:\n\n"
            +
            "\n".join(
                f"#{r['id']} | "
                f"{'خرید' if r['side']=='buy' else 'فروش'} | "
                f"{r['usdt']:g} USDT | "
                f"{r['total']:,.2f} | "
                f"{r['status']}"
                for r in rows
            )
        )

    await q.edit_message_text(
        text,
        reply_markup=user_menu()
    )


async def new_order(
    update,
    context,
    side
):

    q = update.callback_query

    await q.answer()

    rate = float(
        setting(
            "sell_rate"
            if side == "buy"
            else "buy_rate"
        )
    )

    context.user_data["state"] = (
        "order_amount"
    )

    context.user_data["side"] = side

    context.user_data["rate"] = rate

    await q.edit_message_text(

        f"{'🟢 خرید' if side=='buy' else '🔴 فروش'} تتر\n"

        f"نرخ محاسبه: {money(rate)}\n\n"

        "مقدار USDT را فقط به عدد بفرستید:"
    )


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

        if (
            amount <= 0
            or amount > 100000000
        ):
            raise ValueError

    except:

        await update.message.reply_text(
            "لطفاً یک مقدار عددی معتبر وارد کنید."
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

        c = db()

        c.execute(
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

        oid = c.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        c.commit()
        c.close()

    context.user_data.clear()

    await update.message.reply_text(

        f"✅ سفارش #{oid} ثبت شد.\n\n"

        f"نوع: "
        f"{'خرید' if side=='buy' else 'فروش'}\n"

        f"مقدار: {amount:g} USDT\n"

        f"نرخ: {money(rate)}\n"

        f"مبلغ: {money(total)}\n\n"

        "مدیریت پس از بررسی سفارش با شما تماس می‌گیرد.",

        reply_markup=user_menu()
    )

    await notify_admins(

        context,

        f"🔔 سفارش جدید #{oid}\n"

        f"کاربر: "
        f"{update.effective_user.id}\n"

        f"نوع: {side}\n"

        f"مقدار: {amount:g} USDT\n"

        f"مبلغ: {money(total)}"
    )


async def payment(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    context.user_data["state"] = (
        "payment_ref"
    )

    await q.edit_message_text(

        "💳 پرداخت / رسید\n\n"

        "شناسه سفارش و در صورت نیاز "
        "TXID/شماره رسید را در یک پیام بفرستید.\n"

        "مدیریت پس از بررسی وضعیت پرداخت "
        "را تغییر می‌دهد."
    )


async def save_payment_ref(
    update,
    context
):

    ref = update.message.text.strip()

    with db_lock:

        c = db()

        r = c.execute(
            """
            SELECT id
            FROM orders
            WHERE tg_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                update.effective_user.id,
            )
        ).fetchone()

        if r:

            c.execute(
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
                    r["id"]
                )
            )

        c.commit()
        c.close()

    context.user_data.clear()

    await update.message.reply_text(
        "✅ رسید/شناسه پرداخت ثبت شد "
        "و برای مدیریت ارسال گردید.",
        reply_markup=user_menu()
    )

    await notify_admins(
        context,
        f"💳 رسید پرداخت از کاربر "
        f"{update.effective_user.id}: {ref}"
    )


async def ai(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    if setting("ai_enabled") != "1":

        await q.edit_message_text(
            "🤖 دستیار هوشمند فعلاً غیرفعال است.",
            reply_markup=user_menu()
        )

        return

    context.user_data["state"] = "ai"

    await q.edit_message_text(
        "🤖 سوال خود را بفرستید."
    )


async def ai_reply(
    update,
    context
):

    if (
        not OPENAI_API_KEY
        or OpenAI is None
    ):

        await update.message.reply_text(

            "دستیار هوشمند در حال حاضر "
            "تنظیم نشده است.\n"

            "OPENAI_API_KEY را در "
            ".env وارد کنید."
        )

        return

    try:

        client = OpenAI(
            api_key=OPENAI_API_KEY
        )

        r = client.responses.create(

            model=OPENAI_MODEL,

            input=(

                "تو دستیار یک ربات "
                "خرید و فروش تتر هستی. "

                "قیمت یا موجودی را حدس نزن. "

                "نرخ فعلی خرید "
                f"{setting('buy_rate')} "

                "و فروش "
                f"{setting('sell_rate')} "
                "است. "

                "به زبان دری/فارسی کوتاه "
                "و دقیق پاسخ بده.\n\n"

                + update.message.text
            )
        )

        answer = getattr(
            r,
            "output_text",
            None
        ) or "پاسخی دریافت نشد."

        await update.message.reply_text(
            answer
        )

    except Exception:

        log.exception(
            "AI error"
        )

        await update.message.reply_text(
            "فعلاً دستیار هوشمند پاسخ نداد. "
            "بعداً دوباره امتحان کنید."
        )

    context.user_data.clear()


async def support(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    await q.edit_message_text(

        f"📞 پشتیبانی: "
        f"{setting('support')}",

        reply_markup=user_menu()
    )


def admin_stats():

    c = db()

    users = c.execute(
        "SELECT COUNT(*) n FROM users"
    ).fetchone()["n"]

    orders = c.execute(
        "SELECT COUNT(*) n FROM orders"
    ).fetchone()["n"]

    pending = c.execute(
        """
        SELECT COUNT(*) n
        FROM orders
        WHERE status='در انتظار تایید'
        """
    ).fetchone()["n"]

    volume = c.execute(
        """
        SELECT COALESCE(SUM(total),0) n
        FROM orders
        WHERE status NOT IN ('رد شد','لغو شد')
        """
    ).fetchone()["n"]

    c.close()

    return (
        users,
        orders,
        pending,
        volume
    )


async def admin_dashboard(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    u, o, p, v = admin_stats()

    await q.edit_message_text(

        f"📊 داشبورد مدیریت\n\n"

        f"👥 مشتریان: {u}\n"

        f"📦 سفارش‌ها: {o}\n"

        f"⏳ در انتظار: {p}\n"

        f"💰 حجم ثبت‌شده: {v:,.2f}",

        reply_markup=admin_menu()
    )


async def admin_orders(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM orders
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    c.close()

    if not rows:

        text = "📦 سفارشی وجود ندارد."

    else:

        text = (
            "📦 سفارش‌های اخیر:\n\n"
            +
            "\n".join(
                f"#{r['id']} | "
                f"{r['tg_id']} | "
                f"{r['side']} | "
                f"{r['usdt']:g} | "
                f"{r['total']:,.2f} | "
                f"{r['status']}"
                for r in rows
            )
        )

    await q.edit_message_text(

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
    async def admin_rates(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    context.user_data["admin_state"] = (
        "rates"
    )

    await q.edit_message_text(

        f"💵 نرخ فعلی\n"

        f"خرید: {setting('buy_rate')}\n"

        f"فروش: {setting('sell_rate')}\n\n"

        "برای تغییر، این قالب را بفرستید:\n"

        "خرید 70\n"
        "فروش 71"
    )


async def admin_users(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM users
        ORDER BY created_at DESC
        LIMIT 20
        """
    ).fetchall()

    c.close()

    if not rows:

        text = "👥 مشتری‌ای وجود ندارد."

    else:

        text = (
            "👥 مشتریان:\n\n"
            +
            "\n".join(

                f"{r['tg_id']} | "
                f"@{r['username'] or '-'} | "
                f"{'🚫' if r['blocked'] else '✅'}"

                for r in rows
            )
        )

    await q.edit_message_text(

        text,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🚫/✅ مدیریت مسدودسازی",
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


async def admin_block(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    context.user_data["admin_state"] = (
        "block"
    )

    await q.edit_message_text(

        "ID کاربر را برای مسدود کردن "
        "یا آزاد کردن بفرستید.\n\n"

        "مثال:\n"
        "123456789"
    )


async def admin_payments(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM orders
        WHERE payment_ref IS NOT NULL
        ORDER BY id DESC
        LIMIT 15
        """
    ).fetchall()

    c.close()

    if not rows:

        text = (
            "💳 پرداخت ثبت‌شده‌ای وجود ندارد."
        )

    else:

        text = (
            "💳 پرداخت‌ها:\n\n"
            +
            "\n".join(

                f"#{r['id']} | "
                f"{r['tg_id']} | "
                f"{r['payment_status']} | "
                f"{r['payment_ref']}"

                for r in rows
            )
        )

    await q.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


async def admin_reports(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    month = datetime.now().strftime(
        "%Y-%m"
    )

    d = c.execute(
        """
        SELECT
            COUNT(*) n,
            COALESCE(SUM(total),0) s
        FROM orders
        WHERE substr(created_at,1,10)=?
        """,
        (today,)
    ).fetchone()

    m = c.execute(
        """
        SELECT
            COUNT(*) n,
            COALESCE(SUM(total),0) s
        FROM orders
        WHERE substr(created_at,1,7)=?
        """,
        (month,)
    ).fetchone()

    a = c.execute(
        """
        SELECT
            COUNT(*) n,
            COALESCE(SUM(total),0) s
        FROM orders
        """
    ).fetchone()

    c.close()

    await q.edit_message_text(

        f"📈 گزارش معاملات\n\n"

        f"امروز: "
        f"{d['n']} سفارش / "
        f"{d['s']:,.2f}\n"

        f"این ماه: "
        f"{m['n']} سفارش / "
        f"{m['s']:,.2f}\n"

        f"کل: "
        f"{a['n']} سفارش / "
        f"{a['s']:,.2f}",

        reply_markup=admin_menu()
    )


async def admin_broadcast(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    context.user_data["admin_state"] = (
        "broadcast"
    )

    await q.edit_message_text(
        "📢 متن پیام همگانی را بفرستید."
    )


async def admin_settings(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    await q.edit_message_text(

        f"⚙️ تنظیمات\n\n"

        f"نگهداری: "
        f"{'روشن' if setting('maintenance')=='1' else 'خاموش'}\n"

        f"AI: "
        f"{'روشن' if setting('ai_enabled')=='1' else 'خاموش'}\n"

        f"پشتیبانی: "
        f"{setting('support')}\n\n"

        "برای تغییر AI:\n"
        "ai on / ai off\n\n"

        "برای نگهداری:\n"
        "maintenance on / maintenance off",

        reply_markup=admin_menu()
    )


async def admin_logs(
    update,
    context
):

    q = update.callback_query

    await q.answer()

    c = db()

    rows = c.execute(
        """
        SELECT *
        FROM admin_logs
        ORDER BY id DESC
        LIMIT 20
        """
    ).fetchall()

    c.close()

    if rows:

        logs = "\n".join(

            f"{r['created_at']} | "
            f"{r['admin_id']} | "
            f"{r['action']} | "
            f"{r['detail']}"

            for r in rows
        )

    else:

        logs = "خالی"

    text = (
        "🔐 آخرین لاگ‌ها:\n\n"
        + logs
    )

    await q.edit_message_text(
        text,
        reply_markup=admin_menu()
    )


async def callbacks(
    update,
    context
):

    q = update.callback_query

    if q.data == "buy":

        return await new_order(
            update,
            context,
            "buy"
        )

    if q.data == "sell":

        return await new_order(
            update,
            context,
            "sell"
        )

    if q.data == "rates":

        return await rates(
            update,
            context
        )

    if q.data == "profile":

        return await profile(
            update,
            context
        )

    if q.data == "myorders":

        return await myorders(
            update,
            context
        )

    if q.data == "payment":

        return await payment(
            update,
            context
        )

    if q.data == "ai":

        return await ai(
            update,
            context
        )

    if q.data == "support":

        return await support(
            update,
            context
        )

    if not is_admin(
        q.from_user.id
    ):

        await q.answer(
            "دسترسی مجاز نیست.",
            show_alert=True
        )

        return

    if q.data == "adm_dashboard":

        return await admin_dashboard(
            update,
            context
        )

    if q.data == "adm_orders":

        return await admin_orders(
            update,
            context
        )

    if q.data == "adm_users":

        return await admin_users(
            update,
            context
        )

    if q.data == "adm_rates":

        return await admin_rates(
            update,
            context
        )

    if q.data == "adm_payments":

        return await admin_payments(
            update,
            context
        )

    if q.data == "adm_reports":

        return await admin_reports(
            update,
            context
        )

    if q.data == "adm_broadcast":

        return await admin_broadcast(
            update,
            context
        )

    if q.data == "adm_block":

        return await admin_block(
            update,
            context
        )

    if q.data == "adm_settings":

        return await admin_settings(
            update,
            context
        )

    if q.data == "adm_logs":

        return await admin_logs(
            update,
            context
        )

    if q.data == "adm_back":

        return await q.edit_message_text(
            "🔐 پنل مدیریت",
            reply_markup=admin_menu()
        )


async def text_handler(
    update,
    context
):

    ensure_user(
        update.effective_user
    )

    if blocked(
        update.effective_user.id
    ):

        await update.message.reply_text(
            "حساب شما مسدود است."
        )

        return

    state = context.user_data.get(
        "state"
    )

    if state == "order_amount":

        return await create_order_from_amount(
            update,
            context
        )

    if state == "payment_ref":

        return await save_payment_ref(
            update,
            context
        )

    if state == "ai":

        return await ai_reply(
            update,
            context
        )

    if is_admin(
        update.effective_user.id
    ):

        astate = context.user_data.get(
            "admin_state"
        )

        txt = update.message.text.strip()

        if astate == "rates":

            changed = []

            for line in txt.splitlines():

                p = line.split()

                if len(p) == 2:

                    try:

                        val = float(p[1])

                        if p[0] in (
                            "خرید",
                            "buy"
                        ):

                            set_setting(
                                "buy_rate",
                                val
                            )

                            changed.append(
                                f"خرید={val}"
                            )

                        if p[0] in (
                            "فروش",
                            "sell"
                        ):

                            set_setting(
                                "sell_rate",
                                val
                            )

                            changed.append(
                                f"فروش={val}"
                            )

                    except:

                        pass

            context.user_data.pop(
                "admin_state",
                None
            )

            log_admin(
                update.effective_user.id,
                "rates",
                "; ".join(changed)
            )

            await update.message.reply_text(

                "✅ نرخ‌ها بروزرسانی شد.\n"
                +
                "\n".join(changed),

                reply_markup=admin_menu()
            )

            return

        if astate == "block":

            if txt.isdigit():

                uid = int(txt)

                r = user_row(uid)

                if r:

                    new = (
                        0
                        if r["blocked"]
                        else 1
                    )

                    with db_lock:

                        c = db()

                        c.execute(
                            """
                            UPDATE users
                            SET blocked=?
                            WHERE tg_id=?
                            """,
                            (
                                new,
                                uid
                            )
                        )

                        c.commit()
                        c.close()

                    log_admin(
                        update.effective_user.id,
                        "block_toggle",
                        f"{uid} -> {new}"
                    )

                    await update.message.reply_text(

                        f"✅ وضعیت کاربر {uid}: "
                        f"{'مسدود' if new else 'آزاد'}",

                        reply_markup=admin_menu()
                    )

                else:

                    await update.message.reply_text(
                        "کاربر پیدا نشد.",
                        reply_markup=admin_menu()
                    )

            context.user_data.pop(
                "admin_state",
                None
            )

            return

        if astate == "broadcast":

            c = db()

            ids = [
                r["tg_id"]
                for r in c.execute(
                    """
                    SELECT tg_id
                    FROM users
                    WHERE blocked=0
                    """
                ).fetchall()
            ]

            c.close()

            ok = 0

            for uid in ids:

                try:

                    await context.bot.send_message(
                        uid,
                        txt
                    )

                    ok += 1

                except:

                    pass

            context.user_data.pop(
                "admin_state",
                None
            )

            log_admin(
                update.effective_user.id,
                "broadcast",
                f"sent={ok}"
            )

            await update.message.reply_text(

                f"📢 ارسال شد: {ok}",

                reply_markup=admin_menu()
            )

            return

        if txt.lower() in (
            "ai on",
            "ai off"
        ):

            set_setting(
                "ai_enabled",
                "1"
                if txt.lower() == "ai on"
                else "0"
            )

            log_admin(
                update.effective_user.id,
                "ai",
                txt
            )

            await update.message.reply_text(
                "✅ تنظیم شد.",
                reply_markup=admin_menu()
            )

            return

        if txt.lower() in (
            "maintenance on",
            "maintenance off"
        ):

            set_setting(
                "maintenance",
                "1"
                if txt.lower() == "maintenance on"
                else "0"
            )

            log_admin(
                update.effective_user.id,
                "maintenance",
                txt
            )

            await update.message.reply_text(
                "✅ تنظیم شد.",
                reply_markup=admin_menu()
            )

            return

    await update.message.reply_text(
        "از منوی زیر استفاده کنید:",
        reply_markup=user_menu()
    )


@app.get("/")
def health():

    return jsonify({

        "status": "ok",

        "service": "Bitcoin1996Bot",

        "time": now()

    })


def run_web():

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is not set in .env"
        )

    init_db()

    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    application = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_cmd
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callbacks
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    log.info(
        "Bitcoin1996Bot started. "
        "Admin IDs: %s",
        sorted(ADMIN_IDS)
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":

    main()
