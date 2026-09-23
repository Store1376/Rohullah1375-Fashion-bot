import os
import logging
from threading import Thread

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# Web server for Render
# =========================

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


# =========================
# /start
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    user = update.effective_user

    if user:
        name = user.first_name
    else:
        name = "دوست عزیز"

    await update.message.reply_text(
        f"سلام {name} 🌷\n\n"
        "به ربات محمدی فیشن خوش آمدید.\n\n"
        "دستورات موجود:\n"
        "/products - نمایش محصولات\n"
        "/help - راهنما"
    )


# =========================
# Products
# =========================

async def products(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "🛍 محصولات محمدی فیشن\n\n"
        "👗 بخمل نگین‌دار\n"
        "💰 قیمت: ۷۰۰\n\n"
        "برای سفارش با مدیریت تماس بگیرید."
    )


# =========================
# Help
# =========================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "📖 راهنمای ربات\n\n"
        "/start - شروع ربات\n"
        "/products - نمایش محصولات\n"
        "/help - راهنما"
    )


# =========================
# Error handler
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):
    logger.error(
        "Telegram error: %s",
        context.error,
    )


# =========================
# Telegram commands
# =========================

async def post_init(
    application: Application,
):
    await application.bot.set_my_commands(
        [
            ("start", "شروع ربات"),
            ("products", "نمایش محصولات"),
            ("help", "راهنما"),
        ]
    )


# =========================
# Main
# =========================

def main():
    # Start web server for Render
    Thread(
        target=run_web_server,
        daemon=True,
    ).start()

    # Create Telegram application
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("products", products)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    # Error handler
    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Mohammadi Fashion Bot started"
    )

    # Start Telegram polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
