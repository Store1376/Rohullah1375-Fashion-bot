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
# SETTINGS
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
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# RENDER WEB SERVER
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
# DATABASE
# =========================================================

def default_data():
    return {
        "products": [
            {
                "id": 1,
                "name": "بخمل نگین‌دار",
                "price": "۷۰۰",
                "description": "لباس زنانه بخمل نگین‌دار",
                "photo_id": "",
            }
        ],
        "orders": [],
        "customers": [],
        "next_product_id": 2,
        "next_order_id": 1,
    }


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

    except Exception as error:
        logger.error(
            "Could not read data.json: %s",
            error,
        )

        data = default_data()
        save_data(data)
        return data

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

    # برای محصولات قدیمی که photo_id ندارند
    for product in data["products"]:
        if "photo_id" not in product:
            product["photo_id"] = ""

    return data


# =========================================================
# MAIN MENU
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
# ADMIN MENU
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
            )
        ],
        [
            InlineKeyboardButton(
                "📊 آمار",
                callback_data="admin_stats",
            )
        ],
        [
            InlineKeyboardButton(
                "📢 پیام به مشتریان",
                callback_data="admin_broadcast",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 منوی اصلی",
                callback_data="admin_back",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(update: Update):
    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID


# =========================================================
# REGISTER CUSTOMER
# =========================================================

def register_customer(user):
    if not user:
        return

    data = load_data()

    for customer in data["customers"]:
        if customer.get("id") == user.id:
            return

    data["customers"].append(
        {
            "id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
        }
    )

    save_data(data)


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    register_customer(
        update.effective_user
    )

    user = update.effective_user

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
# PRODUCTS
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
        if query:
            await query.edit_message_text(
                "🛍 در حال حاضر محصولی ثبت نشده است.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔙 بازگشت",
                                callback_data="back",
                            )
                        ]
                    ]
                ),
            )
        return

    # اگر از دکمه قبلی آمده باشد
    if query:
        try:
            await query.edit_message_text(
                "🛍 محصولات محمدی فیشن\n\n"
                "لطفاً محصول مورد نظر را انتخاب کنید:"
            )
        except Exception:
            pass

        for product in products:
            product_text = (
                f"👗 {product['name']}\n"
                f"💰 قیمت: {product['price']}\n"
            )

            if product.get("description"):
                product_text += (
                    f"📝 {product['description']}\n"
                )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🛒 سفارش این محصول",
                        callback_data=f"buy_{product['id']}",
                    )
                ]
            ]

            if product.get("photo_id"):
                try:
                    await query.message.reply_photo(
                        photo=product["photo_id"],
                        caption=product_text,
                        reply_markup=InlineKeyboardMarkup(
                            keyboard
                        ),
                    )
                except Exception as error:
                    logger.error(
                        "Could not send product photo: %s",
                        error,
                    )

                    await query.message.reply_text(
                        product_text,
                        reply_markup=InlineKeyboardMarkup(
                            keyboard
                        ),
                    )
            else:
                await query.message.reply_text(
                    product_text,
                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                    ),
                )

        await query.message.reply_text(
            "🌷 محمدی فیشن",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔙 بازگشت",
                            callback_data="back",
                        )
                    ]
                ]
            ),
        )


# =========================================================
# PRODUCTS COMMAND
# =========================================================

async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    register_customer(
        update.effective_user
    )

    data = load_data()

    products = data["products"]

    if not products:
        await update.message.reply_text(
            "🛍 در حال حاضر محصولی ثبت نشده است.",
            reply_markup=main_menu(),
        )
        return

    await update.message.reply_text(
        "🛍 محصولات محمدی فیشن"
    )

    for product in products:
        product_text = (
            f"👗 {product['name']}\n"
            f"💰 قیمت: {product['price']}\n"
        )

        if product.get("description"):
            product_text += (
                f"📝 {product['description']}\n"
            )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 سفارش این محصول",
                    callback_data=f"buy_{product['id']}",
                )
            ]
        ]

        if product.get("photo_id"):
            try:
                await update.message.reply_photo(
                    photo=product["photo_id"],
                    caption=product_text,
                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                    ),
                )
            except Exception as error:
                logger.error(
                    "Could not send photo: %s",
                    error,
                )

                await update.message.reply_text(
                    product_text,
                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                    ),
                )
        else:
            await update.message.reply_text(
                product_text,
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
            )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    text = (
        "ℹ️ راهنمای ربات\n\n"
        "/start - شروع ربات\n"
        "/products - نمایش محصولات\n"
        "/help - راهنما\n"
        "/admin - پنل مدیریت\n\n"
        "برای خرید، وارد بخش محصولات شوید."
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
# CONTACT
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "🛍 مشاهده محصولات",
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
# ORDER STATES
# =========================================================

ORDER_NAME = 1
ORDER_PHONE = 2
ORDER_ADDRESS = 3


# =========================================================
# START ORDER
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

        if query.data.startswith("buy_"):
            try:
                product_id = int(
                    query.data.split("_")[1]
                )

                context.user_data[
                    "order_product_id"
                ] = product_id

            except (ValueError, IndexError):
                pass

        await query.edit_message_text(
            "🛒 ثبت سفارش\n\n"
            "لطفاً نام و نام خانوادگی خود را ارسال کنید:"
        )

    return ORDER_NAME


# =========================================================
# ORDER NAME
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
# ORDER PHONE
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
# ORDER ADDRESS
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

    data = load_data()

    product_id = context.user_data.get(
        "order_product_id"
    )

    product = None

    for item in data["products"]:
        if item["id"] == product_id:
            product = item
            break

    if product is None and data["products"]:
        product = data["products"][0]

    if product:
        product_name = product["name"]
        product_price = product["price"]
    else:
        product_name = "نامشخص"
        product_price = "نامشخص"

    user = update.effective_user

    name = context.user_data.get(
        "order_name",
        "نامشخص",
    )

    phone = context.user_data.get(
        "order_phone",
        "نامشخص",
    )

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
            f"شماره سفارش: #{order_id}",
            reply_markup=main_menu(),
        )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# CANCEL
# =========================================================

async def cancel_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=main_menu(),
        )

    return ConversationHandler.END


# =========================================================
# ADMIN COMMAND
# =========================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not is_admin(update):
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
# ADMIN PRODUCTS
# =========================================================

as
