import os
import sqlite3
import logging
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "shop.db")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Mohammadi Fashion Bot is running."


def run_web_server():
    port = int(os.getenv("PORT", "10000"))
    web_app.run(host="0.0.0.0", port=port)


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price TEXT NOT NULL,
            photo_id TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            price TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def is_admin(user_id):
    return ADMIN_ID != 0 and user_id == ADMIN_ID


def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👗 محصولات", callback_data="products")],
            [InlineKeyboardButton("🛒 سفارش‌های من", callback_data="my_orders")],
            [InlineKeyboardButton("📞 تماس با ما", callback_data="contact")],
            [InlineKeyboardButton("ℹ️ درباره فروشگاه", callback_data="about")],
        ]
    )


def admin_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
            [InlineKeyboardButton("🗑 حذف محصول", callback_data="admin_delete")],
            [InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
            [InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")],
        ]
    )


def menu_for_user(user_id):
    rows = list(main_menu().inline_keyboard)

    if is_admin(user_id):
        rows.append(
            [
                InlineKeyboardButton(
                    "🔐 پنل مدیریت",
                    callback_data="admin",
                )
            ]
        )

    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    name = user.first_name or "دوست عزیز"

    await update.message.reply_text(
        f"سلام {name} 🌹\n\n"
        "به فروشگاه اینترنتی Mohammadi Fashion خوش آمدید.\n"
        "برای دیدن محصولات از دکمه‌های زیر استفاده کنید.",
        reply_markup=menu_for_user(user.id),
    )


async def show_products(update, context):
    query = update.callback_query
    await query.answer()

    conn = get_db()

    products = conn.execute(
        "SELECT * FROM products ORDER BY id DESC"
    ).fetchall()

    conn.close()

    if not products:
        await query.edit_message_text(
            "فعلاً محصولی ثبت نشده است.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🏠 خانه",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )
        return

    await query.edit_message_text("👗 محصولات فروشگاه:")

    for product in products:
        caption = (
            f"👗 {product['name']}\n"
            f"💰 قیمت: {product['price']}"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🛍 سفارش این محصول",
                        callback_data=f"buy:{product['id']}",
                    )
                ]
            ]
        )

        if product["photo_id"]:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=product["photo_id"],
                caption=caption,
                reply_markup=keyboard,
            )
        else:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=caption,
                reply_markup=keyboard,
            )

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="برای بازگشت:",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 خانه",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def buy_start(update, context):
    query = update.callback_query
    await query.answer()

    product_id = int(query.data.split(":")[1])

    conn = get_db()

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()

    conn.close()

    if not product:
        await query.edit_message_text(
            "این محصول دیگر موجود نیست."
        )
        return ConversationHandler.END

    context.user_data["product_id"] = product["id"]
    context.user_data["product_name"] = product["name"]
    context.user_data["price"] = product["price"]

    await query.message.reply_text(
        "لطفاً نام و نام خانوادگی خود را ارسال کنید:"
    )

    return GET_NAME


async def get_name(update, context):
    context.user_data["customer_name"] = (
        update.message.text.strip()
    )

    await update.message.reply_text(
        "حالا شماره تماس خود را ارسال کنید:"
    )

    return GET_PHONE


async def get_phone(update, context):
    phone = update.message.text.strip()

    if len(phone) < 5:
        await update.message.reply_text(
            "شماره تماس صحیح نیست. دوباره ارسال کنید:"
        )
        return GET_PHONE

    context.user_data["phone"] = phone

    data = context.user_data

    text = (
        "📦 اطلاعات سفارش\n\n"
        f"👗 محصول: {data['product_name']}\n"
        f"💰 قیمت: {data['price']}\n"
        f"👤 نام: {data['customer_name']}\n"
        f"📞 تماس: {data['phone']}\n\n"
        "آیا سفارش را ثبت کنم؟"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ ثبت سفارش",
                    callback_data="confirm_order",
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data="cancel_order",
                )
            ],
        ]
    )

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
    )

    return CONFIRM


async def confirm_order(update, context):
    query = update.callback_query
    await query.answer()

    data = context.user_data

    conn = get_db()

    cursor = conn.execute(
        """
        INSERT INTO orders
        (
            user_id,
            name,
            phone,
            product_id,
            product_name,
            price
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            update.effective_user.id,
            data["customer_name"],
            data["phone"],
            data["product_id"],
            data["product_name"],
            data["price"],
        ),
    )

    order_id = cursor.lastrowid

    conn.commit()
    conn.close()

    await query.edit_message_text(
        f"✅ سفارش شما با موفقیت ثبت شد.\n\n"
        f"شماره سفارش: #{order_id}\n"
        "به‌زودی با شما تماس گرفته می‌شود.",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 خانه",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )

    if ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    "📦 سفارش جدید!\n\n"
                    f"شماره: #{order_id}\n"
                    f"👗 محصول: {data['product_name']}\n"
                    f"💰 قیمت: {data['price']}\n"
                    f"👤 نام مشتری: {data['customer_name']}\n"
                    f"📞 شماره تماس: {data['phone']}\n"
                    f"🆔 Telegram ID: {update.effective_user.id}"
                ),
            )
        except Exception as exc:
            logging.error(
                "Could not notify admin: %s",
                exc,
            )

    context.user_data.clear()

    return ConversationHandler.END


async def cancel_order(update, context):
    context.user_data.clear()

    if update.callback_query:
        query = update.callback_query

        await query.answer()

        await query.edit_message_text(
            "❌ سفارش لغو شد.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🏠 خانه",
                            callback_data="home",
                        )
                    ]
                ]
            ),
        )

    elif update.message:
        await update.message.reply_text(
            "❌ سفارش لغو شد.",
            reply_markup=menu_for_user(
                update.effective_user.id
            ),
        )

    return ConversationHandler.END


async def my_orders(update, context):
    query = update.callback_query
    await query.answer()

    conn = get_db()

    orders = conn.execute(
        """
        SELECT *
        FROM orders
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (update.effective_user.id,),
    ).fetchall()

    conn.close()

    if not orders:
        text = "هنوز سفارشی ثبت نکرده‌اید."

    else:
        lines = [
            "🛒 سفارش‌های شما:\n"
        ]

        for order in orders:
            lines.append(
                f"#{order['id']} — "
                f"{order['product_name']} — "
                f"{order['price']}"
            )

        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 خانه",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def static_page(
    update,
    context,
    title,
    body,
):
    query = update.callback_query

    await query.answer()

    await query.edit_message_text(
        f"{title}\n\n{body}",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🏠 خانه",
                        callback_data="home",
                    )
                ]
            ]
        ),
    )


async def admin_panel(update, context):
    query = update.callback_query

    await query.answer()

    if not is_admin(update.effective_user.id):
        await query.edit_message_text(
            "⛔ دسترسی غیرمجاز."
        )
        return

    await query.edit_message_text(
        "🔐 پنل مدیریت",
        reply_markup=admin_menu(),
    )


async def admin_add_start(update, context):
    query = update.callback_query

    await query.answer()

    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    await query.message.reply_text(
        "برای افزودن محصول، نام محصول را ارسال کنید.\n\n"
        "مثال:\n"
        "بخمل نگین‌دار"
    )

    return ADMIN_NAME


async def admin_get_name(update, context):
    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "نام محصول خالی نباشد. دوباره بفرستید:"
        )
        return ADMIN_NAME

    context.user_data["admin_product_name"] = name

    await update.message.reply_text(
        "قیمت محصول را ارسال کنید.\n\n"
        "مثال:\n"
        "۷۰۰"
    )

    return ADMIN_PRICE


async def admin_get_price(update, context):
    price = update.message.text.strip()

    if not price:
        await update.message.reply_text(
            "قیمت خالی نباشد. دوباره بفرستید:"
        )
        return ADMIN_PRICE

    context.user_data["admin_product_price"] = price

    await update.message.reply
