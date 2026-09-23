import os
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
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

# =========================================================
# SETTINGS
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID environment variable is not set")

try:
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise RuntimeError("ADMIN_ID must be a number")


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# FLASK SERVER FOR RENDER
# =========================================================

web_app = Flask(__name__)


@web_app.get("/")
def health_check():
    return "Mohammadi Fashion Bot is running.", 200


def run_web_server():
    port = int(os.getenv("PORT", "10000"))

    web_app.run(
        host="0.0.0.0",
        port=port,
    )


# =========================================================
# CONVERSATION STATES
# =========================================================

NAME, PHONE, ADDRESS = range(3)


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
# PRODUCT MENU
# =========================================================

def product_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🛒 سفارش این محصول",
                callback_data="order",
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="back",
            )
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    if user and user.first_name:
        name = user.first_name
    else:
        name = "دوست عزیز"

    text = (
        f"سلام {name} 🌷\n\n"
        "به ربات فروشگاهی محمدی فیشن خوش آمدید.\n\n"
        "👗 عرضه‌کننده انواع لباس‌های زنانه\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
    )

    await update.message.reply_text(
        text,
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

        text = (
            "🛍 محصولات محمدی فیشن\n\n"
            "👗 بخمل نگین‌دار\n"
            "💰 قیمت: ۷۰۰\n\n"
            "برای ثبت سفارش روی دکمه زیر بزنید."
        )

        await query.edit_message_text(
            text,
            reply_markup=product_menu(),
        )

    elif update.message:
        await update.message.reply_text(
            "🛍 محصولات محمدی فیشن\n\n"
            "👗 بخمل نگین‌دار\n"
            "💰 قیمت: ۷۰۰\n\n"
            "برای ثبت سفارش از منوی ربات استفاده کنید.",
            reply_markup=product_menu(),
        )


# =========================================================
# CONTACT
# =========================================================

async def contact(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

        text = (
            "📞 تماس با مدیریت محمدی فیشن\n\n"
            "برای سفارش یا دریافت معلومات بیشتر، "
            "از گزینه «🛒 ثبت سفارش» استفاده کنید.\n\n"
            "مدیریت سفارش شما را بررسی کرده و با شما تماس می‌گیرد."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 ثبت سفارش",
                    callback_data="order",
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
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
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
        "/help - راهنما\n\n"
        "برای خرید محصول می‌توانید از گزینه "
        "«🛒 ثبت سفارش» استفاده کنید."
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
# START ORDER
# =========================================================

async def start_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query:
        await query.answer()

        await query.edit_message_text(
            "🛒 ثبت سفارش\n\n"
            "لطفاً نام و نام خانوادگی خود را ارسال کنید:"
        )

    return NAME


# =========================================================
# RECEIVE NAME
# =========================================================

async def receive_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return NAME

    name = update.message.text.strip()

    if not name:
        await update.message.reply_text(
            "لطفاً نام خود را وارد کنید:"
        )
        return NAME

    context.user_data["name"] = name

    await update.message.reply_text(
        "📱 لطفاً شماره تماس خود را ارسال کنید:"
    )

    return PHONE


# =========================================================
# RECEIVE PHONE
# =========================================================

async def receive_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return PHONE

    phone = update.message.text.strip()

    if not phone:
        await update.message.reply_text(
            "لطفاً شماره تماس خود را وارد کنید:"
        )
        return PHONE

    context.user_data["phone"] = phone

    await update.message.reply_text(
        "📍 لطفاً آدرس خود را ارسال کنید:"
    )

    return ADDRESS


# =========================================================
# RECEIVE ADDRESS AND SEND ORDER
# =========================================================

async def receive_address(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return ADDRESS

    address = update.message.text.strip()

    if not address:
        await update.message.reply_text(
            "لطفاً آدرس خود را وارد کنید:"
        )
        return ADDRESS

    context.user_data["address"] = address

    user = update.effective_user

    if user:
        username = user.username

        if username:
            username_text = f"@{username}"
        else:
            username_text = "ندارد"

        telegram_id = user.id
    else:
        username_text = "ندارد"
        telegram_id = "نامشخص"

    name = context.user_data.get(
        "name",
        "نامشخص",
    )

    phone = context.user_data.get(
        "phone",
        "نامشخص",
    )

    order_text = (
        "🔔 سفارش جدید\n\n"
        "👗 محصول: بخمل نگین‌دار\n"
        "💰 قیمت: ۷۰۰\n\n"
        f"👤 نام مشتری: {name}\n"
        f"📱 شماره تماس: {phone}\n"
        f"📍 آدرس: {address}\n"
        f"👤 Username: {username_text}\n"
        f"🆔 Telegram ID: {telegram_id}"
    )

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=order_text,
        )

        await update.message.reply_text(
            "✅ سفارش شما با موفقیت ثبت شد.\n\n"
            "از خرید شما از محمدی فیشن سپاسگزاریم 🌷\n"
            "مدیریت سفارش شما را بررسی خواهد کرد.",
            reply_markup=main_menu(),
        )

    except Exception as error:
        logger.error(
            "Could not send order to admin: %s",
            error,
        )

        await update.message.reply_text(
            "⚠️ سفارش دریافت شد، اما ارسال آن برای مدیریت "
            "با مشکل روبه‌رو شد.\n"
            "لطفاً دوباره تلاش کنید یا با مدیریت تماس بگیرید."
        )

    context.user_data.clear()

    return ConversationHandler.END


# =========================================================
# CANCEL ORDER
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
# BUTTON HANDLER
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    data = query.data

    if data == "products":
        await show_products(
            update,
            context,
        )

    elif data == "contact":
        await contact(
            update,
            context,
        )

    elif data == "help":
        await help_command(
            update,
            context,
        )

    elif data == "back":
        await query.answer()

        await query.edit_message_text(
            "🌷 محمدی فیشن\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=main_menu(),
        )


# =========================================================
# COMMAND PRODUCTS
# =========================================================

async def products_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "🛍 محصولات محمدی فیشن\n\n"
        "👗 بخمل نگین‌دار\n"
        "💰 قیمت: ۷۰۰\n\n"
        "برای ثبت سفارش از منوی اصلی استفاده کنید.",
        reply_markup=product_menu(),
    )


# =========================================================
# ERROR HANDLER
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
# BOT COMMANDS
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
        ]
    )


# =========================================================
# MAIN
# =========================================================

def main():
    # Start Render web server
    web_thread = Thread(
        target=run_web_server,
        daemon=True,
    )

    web_thread.start()

    # Create Telegram application
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # =====================================================
    # ORDER CONVERSATION
    # =====================================================

    order_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                start_order,
                pattern="^order$",
            )
        ],
        states={
            NAME: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_name,
                )
            ],
            PHONE: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_phone,
                )
            ],
            ADDRESS: [
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receive_address,
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
        order_conversation
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler,
            pattern="^(products|contact|help|back)$",
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Mohammadi Fashion Bot started successfully."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
