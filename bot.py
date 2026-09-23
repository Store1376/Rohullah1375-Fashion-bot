# -*- coding: utf-8 -*-

import os
import json
import logging
from threading import Thread

from flask import Flask

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# تنظیمات
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_TEXT = os.getenv("ADMIN_ID")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set"
    )

if not ADMIN_ID_TEXT:
    raise RuntimeError(
        "ADMIN_ID environment variable is not set"
    )

try:
    ADMIN_ID = int(ADMIN_ID_TEXT)
except ValueError:
    raise RuntimeError(
        "ADMIN_ID must be a number"
    )


DATA_FILE = "data.json"


# =========================================================
# لاگ
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# وب‌سرور Render
# =========================================================

web_app = Flask(__name__)


@web_app.get("/")
def health_check():
    return "Mohammadi Fashion Bot is running.", 200


def run_web_server():
    port = int(
        os.getenv(
            "PORT",
            "10000",
        )
    )

    web_app.run(
        host="0.0.0.0",
        port=port,
    )


# =========================================================
# دیتابیس ساده JSON
# =========================================================

def default_data():
    return {
        "products": [
            {
                "id": 1,
                "name": "بخمل نگین‌دار",
                "price": "۷۰۰",
                "description": "لباس زنانه بخمل نگین‌دار",
            }
        ],
        "orders": [],
        "customers": [],
        "next_product_id": 2,
        "next_order_id": 1,
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        data = default_data()
        save_data(data)
        return data

    try:
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if "products" not in data:
            data["products"] = []

        if "orders" not in data:
            data["orders"] = []

        if "customers" not in data:
            data["customers"] = []

        if "next_product_id" not in data:
            data["next_product_id"] = 1

        if "next_order_id" not in data:
            data["next_order_id"] = 1

        return data

    except Exception as error:
        logger.error(
            "Could not read data.json: %s",
            error,
        )

        data = default_data()
        save_data(data)
        return data


def save_data(data):
    temporary_file = DATA_FILE + ".tmp"

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temporary_file,
        DATA_FILE,
    )


# =========================================================
# منوی اصلی مشتری
# =========================================================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🛍 محصولات",
                callback_data="products",
            )
        ],
        [
            InlineKeyboardButton(
                "🛒 ثبت سفارش",
                callback_data="order",
            )
        ],
        [
            InlineKeyboardButton(
                "📞 تماس با مدیریت",
                callback_data="contact",
            )
        ],
        [
            InlineKeyboardButton(
                "ℹ️ راهنما",
                callback_data="help",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# پنل مدیریت
# =========================================================

def admin_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "📦 محصولات",
                callback_data="admin_products",
            ),
            InlineKeyboardButton(
                "🛒 سفارش‌ها",
                callback_data="admin_orders",
            ),
        ],
        [
            InlineKeyboardButton(
                "➕ افزودن محصول",
                callback_data="admin_add",
            ),
        ],
        [
            InlineKeyboardButton(
                "📊 آمار",
                callback_data="admin_stats",
            ),
        ],
        [
            InlineKeyboardButton(
                "📢 پیام به مشتریان",
                callback_data="admin_broadcast",
            ),
        ],
        [
            InlineKeyboardButton(
                "🔙 منوی اصلی",
                callback_data="admin_back",
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# بررسی مدیر
# =========================================================

def is_admin(update: Update):
    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID


# =========================================================
# ثبت مشتری
# =========================================================

def register_customer(user):
    if not user:
        return

    data = load_data()

    customer_ids = []

    for customer in data["customers"]:
        customer_ids.append(
            customer.get("id")
        )

    if user.id not in customer_ids:
        data["customers"].append(
            {
                "id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
            }
        )

        save_data(data)


# =========================================================
# /start
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    register_customer(user)

    if user and user.first_name:
        name = user.first_name
    else:
        name = "دوست عزیز"

    await update.message.reply_text(
        f"سلام {name} 🌷\n\n"
        "به ربات فروشگاهی محمدی فیشن خوش آمدید.\n\n"
        "👗 عرضه‌کننده انواع لباس‌های زنانه\n\n"
        "لطفاً گزینه مورد نظر خود را انتخاب کنید:",
        reply_markup=main_menu(),
    )


# =========================================================
# نمایش محصولات
# =========================================================

async def show_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

    data = load_data()

    products = data["products"]

    if not products:
        text = "🛍 در حال حاضر محصولی ثبت نشده است."

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="back",
                )
            ]
        ]

        if query:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
            )

        return

    text = "🛍 محصولات محمدی فیشن\n\n"

    keyboard = []

    for product in products:
        text += (
            f"👗 {product['name']}\n"
            f"💰 قیمت: {product['price']}\n"
        )

        if product.get("description"):
            text += (
                f"📝 {product['description']}\n"
            )

        text += "\n"

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🛒 سفارش {product['name']}",
                    callback_data=f"buy_{product['id']}",
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back",
            )
        ]
    )

    markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(
            text,
            reply_markup=markup,
        )


# =========================================================
# دستور /products
# =========================================================

async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    register_customer(
        update.effective_user
    )

    await show_products(
        update,
        context,
    )


# =========================================================
# راهنما
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "ℹ️ راهنمای ربات\n\n"
        "/start - شروع ربات\n"
        "/products - نمایش محصولات\n"
        "/help - راهنما\n\n"
        "برای خرید محصول، وارد بخش محصولات شوید."
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=main_menu(),
        )

    elif update.callback_query:
        await update.callback_query.answer()

        await update.callback_query.edit_message_text(
            text,
            reply_markup=main_menu(),
        )


# =========================================================
# تماس با مدیریت
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 ثبت سفارش",
                    callback_data="products",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="back",
                )
            ],
        ]

        await query.edit_message_text(
            "📞 تماس با مدیریت محمدی فیشن\n\n"
            "برای ثبت سفارش از بخش محصولات استفاده کنید.\n\n"
            "مدیریت پس از دریافت سفارش با شما تماس می‌گیرد.",
            reply_markup=InlineKeyboardMarkup(
                keyboard
            ),
        )


# =========================================================
# وضعیت‌های ثبت سفارش
# =========================================================

ORDER_NAME = 1
ORDER_PHONE = 2
ORDER_ADDRESS = 3


# =========================================================
# شروع سفارش
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

    product_id = None

    if query and query.data.startswith("buy_"):
        try:
            product_id = int(
                query.data.split("_")[1]
            )
        except ValueError:
            product_id = None

    if product_id is not None:
        context.user_data[
            "order_product_id"
        ] = product_id

    if query:
        await query.edit_message_text(
            "🛒 ثبت سفارش\n\n"
            "لطفاً نام و نام خانوادگی خود را ارسال کنید:"
        )

    return ORDER_NAME


# =========================================================
# دریافت نام
# =========================================================

async def receive_order_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ORDER_NAME

    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "لطفاً نام خود را وارد کنید:"
        )
        return ORDER_NAME

    context.user_data[
        "order_name"
    ] = name

    await update.message.reply_text(
        "📱 لطفاً شماره تماس خود را ارسال کنید:"
    )

    return ORDER_PHONE


# =========================================================
# دریافت شماره
# =========================================================

async def receive_order_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ORDER_PHONE

    phone = update.message.text.strip()

    if not phone:
        await update.message.reply_text(
            "لطفاً شماره تماس خود را وارد کنید:"
        )
        return ORDER_PHONE

    context.user_data[
        "order_phone"
    ] = phone

    await update.message.reply_text(
        "📍 لطفاً آدرس خود را ارسال کنید:"
    )

    return ORDER_ADDRESS


# =========================================================
# دریافت آدرس و ثبت سفارش
# =========================================================

async def receive_order_address(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ORDER_ADDRESS

    address = update.message.text.strip()

    if not address:
        await update.message.reply_text(
            "لطفاً آدرس خود را وارد کنید:"
        )
        return ORDER_ADDRESS

    user = update.effective_user

    data = load_data()

    product_id = context.user_data.get(
        "order_product_id"
    )

    product = None

    for item in data["products"]:
        if item["id"] == product_id:
            product = item
            break

    if product is None:
        if data["products"]:
            product = data["products"][0]

    if product:
        product_name = product["name"]
        product_price = product["price"]
    else:
        product_name = "نامشخص"
        product_price = "نامشخص"

    name = context.user_data.get(
        "order_name",
        "نامشخص",
    )

    phone = context.user_data.get(
        "order_phone",
        "نامشخص",
    )

    username = ""

    if user and user.username:
        username = f"@{user.username}"
    else:
        username = "ندارد"

    telegram_id = (
        user.id
        if user
        else "نامشخص"
    )

    order_id = data["next_order_id"]

    order = {
        "id": order_id,
        "product_id": product_id,
        "product_name": product_name,
        "price": product_price,
        "name": name,
        "phone": phone,
        "address": address,
        "username": username,
        "telegram_id": telegram_id,
        "status": "جدید",
    }

    data["orders"].append(order)

    data["next_order_id"] += 1

    save_data(data)

    order_text = (
        "🔔 سفارش جدید\n\n"
        f"🔢 شماره سفارش: #{order_id}\n\n"
        f"👗 محصول: {product_name}\n"
        f"💰 قیمت: {product_price}\n\n"
        f"👤 نام مشتری: {name}\n"
        f"📱 شماره تماس: {phone}\n"
        f"📍 آدرس: {address}\n"
        f"👤 Username: {username}\n"
        f"🆔 Telegram ID: {telegram_id}"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
        )

        await update.message.reply_text(
            "✅ سفارش شما با موفقیت ثبت شد.\n\n"
            f"🔢 شماره سفارش: #{order_id}\n"
            f"👗 محصول: {product_name}\n"
            f"💰 قیمت: {product_price}\n\n"
            "از خرید شما از محمدی فیشن سپاسگزاریم 🌷",
            reply_markup=main_menu(),
        )

    except Exception as error:
        logger.error(
            "Could not notify admin: %s",
            error,
        )

        await update.message.reply_text(
            "⚠️ سفارش در سیستم ثبت شد، "
            "اما اطلاع‌رسانی به مدیریت با مشکل مواجه شد.\n\n"
            f"شماره سفارش شما: #{order_id}",
            reply_markup=main_menu(),
        )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# لغو سفارش
# =========================================================

async def cancel_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "❌ سفارش لغو شد.",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# =========================================================
# پنل مدیریت
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        if update.message:
            await update.message.reply_text(
                "⛔ دسترسی غیرمجاز."
            )
        return

    await update.message.reply_text(
        "🔐 پنل مدیریت محمدی فیشن\n\n"
        "لطفاً یک گزینه را انتخاب کنید:",
        reply_markup=admin_menu(),
    )


# =========================================================
# نمایش محصولات در پنل مدیریت
# =========================================================

async def admin_products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return

    await query.answer()

    data = load_data()

    products = data["products"]

    if not products:
        text = (
            "📦 محصولات\n\n"
            "هنوز محصولی ثبت نشده است."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "➕ افزودن محصول",
                    callback_data="admin_add",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 پنل مدیریت",
                    callback_data="admin_home",
                )
            ],
        ]

    else:
        text = "📦 محصولات ثبت‌شده:\n\n"

        keyboard = []

        for product in products:
            text += (
                f"🆔 {product['id']}\n"
                f"👗 {product['name']}\n"
                f"💰 {product['price']}\n\n"
            )

            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✏️ {product['name']}",
                        callback_data=f"edit_{product['id']}",
                    ),
                    InlineKeyboardButton(
                        "🗑 حذف",
                        callback_data=f"delete_{product['id']}",
                    ),
                ]
            )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "➕ افزودن محصول",
                    callback_data="admin_add",
                )
            ]
        )

        keyboard.append(
            [
                InlineKeyboardButton(
                    "🔙 پنل مدیریت",
                    callback_data="admin_home",
                )
            ]
        )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# افزودن محصول
# =========================================================

ADD_PRODUCT_NAME = 10
ADD_PRODUCT_PRICE = 11
ADD_PRODUCT_DESCRIPTION = 12


async def admin_add_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        return ConversationHandler.END

    query = update.callback_query

    if query:
        await query.answer()

        await query.edit_message_text(
            "➕ افزودن محصول\n\n"
            "نام محصول را ارسال کنید:"
        )

    return ADD_PRODUCT_NAME


async def receive_product_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ADD_PRODUCT_NAME

    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "نام محصول نمی‌تواند خالی باشد."
        )
        return ADD_PRODUCT_NAME

    context.user_data[
        "new_product_name"
    ] = name

    await update.message.reply_text(
        "💰 قیمت محصول را ارسال کنید:"
    )

    return ADD_PRODUCT_PRICE


async def receive_product_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ADD_PRODUCT_PRICE

    price = update.message.text.strip()

    if not price:
        await update.message.reply_text(
            "لطفاً قیمت را وارد کنید."
        )
        return ADD_PRODUCT_PRICE

    context.user_data[
        "new_product_price"
    ] = price

    await update.message.reply_text(
        "📝 توضیحات محصول را ارسال کنید.\n\n"
        "اگر توضیحی ندارید، فقط بنویسید: ندارد"
    )

    return ADD_PRODUCT_DESCRIPTION


async def receive_product_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ADD_PRODUCT_DESCRIPTION

    description = update.message.text.strip()

    if description == "ندارد":
        description = ""

    data = load_data()

    product_id = data["next_product_id"]

    product = {
        "id": product_id,
        "name": context.user_data.get(
            "new_product_name",
            "محصول",
        ),
        "price": context.user_data.get(
            "new_product_price",
            "۰",
        ),
        "description": description,
    }

    data["products"].append(product)

    data["next_product_id"] += 1

    save_data(data)

    context.user_data.clear()

    await update.message.reply_text(
        "✅ محصول با موفقیت اضافه شد.\n\n"
        f"👗 {product['name']}\n"
        f"💰 {product['price']}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# حذف محصول
# =========================================================

async def delete_product(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        product_id = int(
            query.data.split("_")[1]
        )
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ شناسه محصول نامعتبر است.",
            reply_markup=admin_menu(),
        )
        return

    data = load_data()

    old_count = len(
        data["products"]
    )

    data["products"] = [
        product
        for product in data["products"]
        if product["id"] != product_id
    ]

    if len(data["products"]) == old_count:
        await query.edit_message_text(
            "❌ محصول پیدا نشد.",
            reply_markup=admin_menu(),
        )
        return

    save_data(data)

    await query.edit_message_text(
        "✅ محصول حذف شد.",
        reply_markup=admin_menu(),
    )


# =========================================================
# سفارش‌ها
# =========================================================

async def admin_orders(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return

    await query.answer()

    data = load_data()

    orders = data["orders"]

    if not orders:
        text = (
            "🛒 سفارش‌ها\n\n"
            "هنوز سفارشی ثبت نشده است."
        )

    else:
        recent_orders = orders[-10:]

        text = (
            "🛒 آخرین سفارش‌ها\n\n"
        )

        for order in reversed(
            recent_orders
        ):
            text += (
                f"🔢 #{order['id']}\n"
                f"👗 {order['product_name']}\n"
                f"💰 {order['price']}\n"
                f"👤 {order['name']}\n"
                f"📱 {order['phone']}\n"
                f"📍 {order['address']}\n"
                f"📌 وضعیت: {order['status']}\n"
                "────────────\n"
            )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 پنل مدیریت",
                callback_data="admin_home",
            )
        ]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# آمار
# =========================================================

async def admin_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return

    await query.answer()

    data = load_data()

    products_count = len(
        data["products"]
    )

    orders_count = len(
        data["orders"]
    )

    customers_count = len(
        data["customers"]
    )

    text = (
        "📊 آمار محمدی فیشن\n\n"
        f"📦 تعداد محصولات: {products_count}\n"
        f"🛒 تعداد سفارش‌ها: {orders_count}\n"
        f"👥 تعداد مشتریان: {customers_count}\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 پنل مدیریت",
                callback_data="admin_home",
            )
        ]
    ]

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# =========================================================
# پیام همگانی
# =========================================================

BROADCAST_MESSAGE = 20


async def admin_broadcast_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
        return ConversationHandler.END

    query = update.callback_query

    if query:
        await query.answer()

        await query.edit_message_text(
            "📢 ارسال پیام به مشتریان\n\n"
            "متن پیام را ارسال کنید:"
        )

    return BROADCAST_MESSAGE


async def admin_broadcast_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ConversationHandler.END

    if not is_admin(update):
        return ConversationHandler.END

    message_text = update.message.text.strip()

    if not message_text:
        await update.message.reply_text(
            "پیام نمی‌تواند خالی باشد."
        )
        return BROADCAST_MESSAGE

    data = load_data()

    customers = data["customers"]

    success = 0
    failed = 0

    for customer in customers:
        customer_id = customer.get("id")

        if not customer_id:
            continue

        try:
            await context.bot.send_message(
                chat_id=customer_id,
                text=message_text,
            )

            success += 1

        except Exception as error:
            failed += 1

            logger.warning(
                "Broadcast failed for %s: %s",
                customer_id,
                error,
            )

    await update.message.reply_text(
        "📢 ارسال پیام تمام شد.\n\n"
        f"✅ ارسال موفق: {success}\n"
        f"❌ ارسال ناموفق: {failed}",
        reply_markup=admin_menu(),
    )

    return ConversationHandler.END


# =========================================================
# ویرایش محصول
# =========================================================

EDIT_PRODUCT_NAME = 30
EDIT_PRODUCT_PRICE = 31
EDIT_PRODUCT_DESCRIPTION = 32


async def edit_product_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return ConversationHandler.END

    await query.answer()

    try:
        product_id = int(
            query.data.split("_")[1]
        )
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ شناسه محصول نامعتبر است.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    data = load_data()

    product = None

    for item in data["products"]:
        if item["id"] == product_id:
            product = item
            break

    if product is None:
        await query.edit_message_text(
            "❌ محصول پیدا نشد.",
            reply_markup=admin_menu(),
        )
        return ConversationHandler.END

    context.user_data[
        "edit_product_id"
    ] = product_id

    await query.edit_message_text(
        "✏️ ویرایش محصول\n\n"
        f"نام فعلی: {product['name']}\n\n"
        "نام جدید را ارسال کنید:"
    )

    return EDIT_PRODUCT_NAME


async def receive_edit_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return EDIT_PRODUCT_NAME

    name = update.message.text.strip()

    if not name:
        return EDIT_PRODUCT_NAME

    context.user_data[
        "edit_product_name"
    ] = name

    await update.message.reply_text(
        "💰 قیمت جدید را ارسال کنید:"
    )

    return EDIT_PRODUCT_PRICE


async def receive_edit_price(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return EDIT_PRODUCT_PRICE

    price = update.message.text.strip()

    if not price:
        return EDIT_PRODUCT_PRICE

    context.user_data[
        "edit_product_price"
    ] = price

    await update.message.reply_text(
        "📝 توضیحات جدید را ارسال کنید.\n\n"
        "اگر توضیحی ندارید، بنویسید: ندارد"
    )

    return EDIT_PRODUCT_DESCRIPTION


async def receive_edit_description(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return EDIT_PRODUCT_DESCRIPTION

    description = update.message.text.strip()

    if description == "ندارد":
        description = ""

    product_id = context.user_data.get(
        "edit_product_id"
    )

    data = load_data()

    updated = False

    for product in data["products"]:
        if product["id"] == product_id:
            product["name"] = context.user_data.get(
                "edit_product_name",
                product["name"],
            )

            product["price"] = context.user_data.get(
                "edit_product_price",
                product["price"],
            )

            product["description"] = description

            updated = True
            break

    if updated:
        save_data(data)

        await update.message.reply_text(
            "✅ محصول با موفقیت ویرایش شد.",
            reply_markup=admin_menu(),
        )
    else:
        await update.message.reply_text(
            "❌ محصول پیدا نشد.",
            reply_markup=admin_menu(),
        )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# دکمه‌های عمومی
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    data = query.data

    # -----------------------------------------------------
    # عمومی
    # -----------------------------------------------------

    if data == "products":
        await show_products(
            update,
            context,
        )
        return

    if data == "contact":
        await contact(
            update,
            context,
        )
        return

    if data == "help":
        await help_command(
            update,
            context,
        )
        return

    if data == "back":
        await query.answer()

        await query.edit_message_text(
            "🌷 محمدی فیشن\n\n"
            "لطفاً گزینه مورد نظر خود را انتخاب کنید:",
            reply_markup=main_menu(),
        )

        return

    # -----------------------------------------------------
    # سفارش محصول
    # -----------------------------------------------------

    if data.startswith("buy_"):
        return

    # -----------------------------------------------------
    # پنل مدیریت
    # -----------------------------------------------------

    if not is_admin(update):
        await query.answer(
            "⛔ دسترسی غیرمجاز.",
            show_alert=True,
        )
        return

    if data == "admin_home":
        await query.answer()

        await query.edit_message_text(
            "🔐 پنل مدیریت محمدی فیشن\n\n"
            "لطفاً یک گزینه را انتخاب کنید:",
            reply_markup=admin_menu(),
        )

        return

    if data == "admin_back":
        await query.answer()

        await query.edit_message_text(
            "🌷 منوی اصلی",
            reply_markup=main_menu(),
        )

        return

    if data == "admin_products":
        await admin_products(
            update,
            context,
        )
        return

    if data == "admin_orders":
        await admin_orders(
            update,
            context,
        )
        return

    if data == "admin_stats":
        await admin_stats(
            update,
            context,
        )
        return


# =========================================================
# خطا
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Telegram error: %s",
        context.error,
    )


# =========================================================
# دستورات ربات
# =========================================================

async def post_init(
    application: Application,
):
    await application.bot.set_my_commands(
        [
            (
                "start",
                "شروع ربات",
            ),
            (
                "products",
                "نمایش محصولات",
            ),
            (
                "help",
                "راهنما",
            ),
            (
                "admin",
                "پنل مدیریت",
            ),
        ]
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # -----------------------------------------------------
    # Render web server
    # -----------------------------------------------------

    web_thread = Thread(
        target=run_web_server,
        daemon=True,
    )

    web_thread.start()

    # -----------------------------------------------------
    # Telegram application
    # -----------------------------------------------------

    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # -----------------------------------------------------
    # سفارش
    # -----------------------------------------------------

    order_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_order,
                pattern=r"^(order|buy_\d+)$",
            )
        ],
        states={
            ORDER_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_order_name,
                )
            ],
            ORDER_PHONE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_order_phone,
                )
            ],
            ORDER_ADDRESS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_order_address,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            )
        ],
        allow_reentry=True,
    )

    # -----------------------------------------------------
    # افزودن محصول
    # -----------------------------------------------------

    add_product_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_add_product,
                pattern=r"^admin_add$",
            )
        ],
        states={
            ADD_PRODUCT_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_product_name,
                )
            ],
            ADD_PRODUCT_PRICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_product_price,
                )
            ],
            ADD_PRODUCT_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_product_description,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            )
        ],
        allow_reentry=True,
    )

    # -----------------------------------------------------
    # ویرایش محصول
    # -----------------------------------------------------

    edit_product_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_product_start,
                pattern=r"^edit_\d+$",
            )
        ],
        states={
            EDIT_PRODUCT_NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_name,
                )
            ],
            EDIT_PRODUCT_PRICE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_price,
                )
            ],
            EDIT_PRODUCT_DESCRIPTION: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_edit_description,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            )
        ],
        allow_reentry=True,
    )

    # -----------------------------------------------------
    # پیام همگانی
    # -----------------------------------------------------

    broadcast_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_broadcast_start,
                pattern=r"^admin_broadcast$",
            )
        ],
        states={
            BROADCAST_MESSAGE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    admin_broadcast_send,
                )
            ]
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                cancel_order,
            )
        ],
        allow_reentry=True,
    )

    # -----------------------------------------------------
    # دستورات
    # -----------------------------------------------------

    application.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    application.add_handler(
        CommandHandler(
            "products",
            products_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command,
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command,
        )
    )

    # -----------------------------------------------------
    # Conversation handlers
    # -----------------------------------------------------

    application.add_handler(
        order_conversation
    )

    application.add_handler(
        add_product_conversation
    )

    application.add_handler(
        edit_product_conversation
    )

    application.add_handler(
        broadcast_conversation
    )

    # -----------------------------------------------------
    # حذف محصول
    # -----------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            delete_product,
            pattern=r"^delete_\d+$",
        )
    )

    # -----------------------------------------------------
    # سایر دکمه‌ها
    # -----------------------------------------------------

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # -----------------------------------------------------
    # Error handler
    # -----------------------------------------------------

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Mohammadi Fashion Bot started successfully."
    )

    # -----------------------------------------------------
    # Polling
    # -----------------------------------------------------

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
