import os
import sqlite3
import threading
from datetime import datetime

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
PORT = int(os.getenv("PORT", "10000"))

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

app = Flask(__name__)
lock = threading.Lock()


def db():
    conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with lock:
        conn = db()

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """)

        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key,value)
            VALUES('buy_rate','70')
            """
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO settings(key,value)
            VALUES('sell_rate','69')
            """
        )

        conn.commit()
        conn.close()


def setting(key):
    conn = db()

    row = conn.execute(
        "SELECT value FROM settings WHERE key=?",
        (key,)
    ).fetchone()

    conn.close()

    return row["value"] if row else ""


def is_admin(user_id):
    return user_id in ADMIN_IDS


def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📊 داشبورد",
                callback_data="admin_dashboard"
            ),
            InlineKeyboardButton(
                "👥 کاربران",
                callback_data="admin_users"
            ),
        ],
        [
            InlineKeyboardButton(
                "📦 سفارش‌ها",
                callback_data="admin_orders"
            ),
            InlineKeyboardButton(
                "💵 نرخ‌ها",
                callback_data="admin_rates"
            ),
        ],
        [
            InlineKeyboardButton(
                "💳 پرداخت‌ها",
                callback_data="admin_payments"
            ),
            InlineKeyboardButton(
                "📈 گزارش‌ها",
                callback_data="admin_reports"
            ),
        ],
        [
            InlineKeyboardButton(
                "⚙️ تنظیمات",
                callback_data="admin_settings"
            ),
            InlineKeyboardButton(
                "🔐 امنیت",
                callback_data="admin_security"
            ),
        ],
    ])


@app.get("/")
def home():
    return "Bitcoin1996Bot is running!"


@app.get("/health")
def health():
    return "OK"


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    with lock:
        conn = db()

        conn.execute(
            """
            INSERT OR REPLACE INTO users(
                id,
                username,
                first_name,
                created_at
            )
            VALUES(
                ?,
                ?,
                ?,
                COALESCE(
                    (
                        SELECT created_at
                        FROM users
                        WHERE id=?
                    ),
                    ?
                )
            )
            """,
            (
                user.id,
                user.username or "",
                user.first_name or "",
                user.id,
                datetime.now().isoformat()
            )
        )

        conn.commit()
        conn.close()

    await update.message.reply_text(
        "✅ ربات فعال است!\n\n"
        "Bitcoin1996Bot با موفقیت اجرا شد.\n\n"
        "برای مدیریت ربات، دستور /admin را بزنید."
    )


async def admin_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text(
            "⛔ شما دسترسی مدیریت ندارید."
        )
        return

    await update.message.reply_text(
        "🔐 پنل مدیریت\n\n"
        "یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=admin_keyboard()
    )


async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if not is_admin(query.from_user.id):
        await query.answer(
            "⛔ دسترسی مجاز نیست.",
            show_alert=True
        )
        return

    await query.answer()

    data = query.data
    conn = db()

    if data == "admin_dashboard":

        users = conn.execute(
            "SELECT COUNT(*) AS n FROM users"
        ).fetchone()["n"]

        orders = conn.execute(
            "SELECT COUNT(*) AS n FROM orders"
        ).fetchone()["n"]

        await query.edit_message_text(
            "📊 داشبورد مدیریت\n\n"
            f"👥 کاربران: {users}\n"
            f"📦 سفارش‌ها: {orders}\n\n"
            f"🟢 نرخ خرید: {setting('buy_rate')}\n"
            f"🔴 نرخ فروش: {setting('sell_rate')}",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_users":

        users = conn.execute(
            """
            SELECT id, first_name, username
            FROM users
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

        if not users:
            text = "👥 هنوز کاربری ثبت نشده است."

        else:
            lines = [
                "👥 آخرین کاربران:"
            ]

            for row in users:

                name = (
                    row["first_name"]
                    or "بدون نام"
                )

                username = (
                    f"@{row['username']}"
                    if row["username"]
                    else "بدون یوزرنیم"
                )

                lines.append(
                    f"• {name} | "
                    f"{username} | "
                    f"ID: {row['id']}"
                )

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            reply_markup=admin_keyboard()
        )

    elif data == "admin_orders":

        orders = conn.execute(
            """
            SELECT
                id,
                user_id,
                side,
                amount,
                status,
                created_at
            FROM orders
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

        if not orders:
            text = "📦 هنوز سفارشی ثبت نشده است."

        else:
            lines = [
                "📦 آخرین سفارش‌ها:"
            ]

            for row in orders:

                lines.append(
                    f"#{row['id']} | "
                    f"{row['side']} | "
                    f"{row['amount']} USDT | "
                    f"{row['status']} | "
                    f"{row['user_id']}"
                )

            text = "\n".join(lines)

        await query.edit_message_text(
            text,
            reply_markup=admin_keyboard()
        )

    elif data == "admin_rates":

        text = (
            "💵 نرخ‌ها\n\n"
            f"🟢 خرید: {setting('buy_rate')}\n"
            f"🔴 فروش: {setting('sell_rate')}\n\n"
            "تغییر نرخ در مرحله بعد اضافه می‌شود."
        )

        await query.edit_message_text(
            text,
            reply_markup=admin_keyboard()
        )

    elif data == "admin_payments":

        await query.edit_message_text(
            "💳 پرداخت‌ها\n\n"
            "ماژول پرداخت در مرحله بعد اضافه می‌شود.",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_reports":

        total = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM orders
            """
        ).fetchone()["n"]

        await query.edit_message_text(
            f"📈 گزارش‌ها\n\n"
            f"تعداد کل سفارش‌ها: {total}",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_settings":

        await query.edit_message_text(
            "⚙️ تنظیمات\n\n"
            "پنل تنظیمات در مرحله بعد تکمیل می‌شود.",
            reply_markup=admin_keyboard()
        )

    elif data == "admin_security":

        await query.edit_message_text(
            "🔐 امنیت\n\n"
            "دسترسی پنل فقط برای مدیر تعیین‌شده "
            "در ADMIN_ID یا ADMIN_IDS فعال است.",
            reply_markup=admin_keyboard()
        )

    conn.close()


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
            "BOT_TOKEN تنظیم نشده است."
        )

    if not ADMIN_IDS:
        raise RuntimeError(
            "ADMIN_ID یا ADMIN_IDS تنظیم نشده است."
        )

    init_db()

    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    bot = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    bot.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    bot.add_handler(
        CommandHandler(
            "admin",
            admin_cmd
        )
    )

    bot.add_handler(
        CallbackQueryHandler(
            admin_callback,
            pattern=r"^admin_"
        )
    )

    print(
        "✅ Bitcoin1996Bot is running..."
    )

    print(
        f"✅ Web server running on port {PORT}"
    )

    print(
        f"✅ Admin IDs: {sorted(ADMIN_IDS)}"
    )

    bot.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
