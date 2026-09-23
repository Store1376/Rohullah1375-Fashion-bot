import os
import threading

from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

app = Flask(__name__)


@app.get("/")
def home():
    return "Bitcoin1996Bot is running!"


@app.get("/health")
def health():
    return "OK"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ ربات فعال است!\n\n"
        "Bitcoin1996Bot با موفقیت اجرا شد."
    )


def run_web():
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    # باز کردن پورت برای Render
    threading.Thread(
        target=run_web,
        daemon=True
    ).start()

    # اجرای Telegram Bot
    bot = Application.builder().token(BOT_TOKEN).build()

    bot.add_handler(
        CommandHandler("start", start)
    )

    print("✅ Bitcoin1996Bot is running...")
    print(f"✅ Web server running on port {PORT}")

    bot.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
