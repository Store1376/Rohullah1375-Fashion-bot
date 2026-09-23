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
filters,
ConversationHandler
)

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "shop.db")

logging.basicConfig(
format="%(asctime)s | %(levelname)s | %(message)s",
level=logging.INFO
)

app_web = Flask(name)
@app_web.get("/")
def home():
    return "Mohammadi Fashion Bot is running."

def web_server():
    port = int(os.getenv("PORT", "10000"))
app_web.run(host="0.0.0.0", port=port)

def db():
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
return conn

def init_db():
conn = db()

conn.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price TEXT NOT NULL,
        photo_id TEXT
    )
""")

conn.execute("""
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
""")

conn.commit()
conn.close()

def is_admin(user_id):
return ADMIN_ID != 0 and user_id == ADMIN_ID

def main_menu():
return InlineKeyboardMarkup([
[InlineKeyboardButton("👗 محصولات", callback_data="products")],
[InlineKeyboardButton("🛒 سفارش‌های من", callback_data="my_orders")],
[InlineKeyboardButton("📞 تماس با ما", callback_data="contact")],
[InlineKeyboardButton("ℹ️ درباره فروشگاه", callback_data="about")]
])

def admin_menu():
return InlineKeyboardMarkup([
[InlineKeyboardButton("➕ افزودن محصول", callback_data="admin_add")],
[InlineKeyboardButton("🗑 حذف محصول", callback_data="admin_delete")],
[InlineKeyboardButton("📦 سفارش‌ها", callback_data="admin_orders")],
[InlineKeyboardButton("🏠 منوی اصلی", callback_data="home")]
])

def add_admin_button(keyboard):
rows = list(keyboard.inline_keyboard)

rows.append([
    InlineKeyboardButton(
        "🔐 پنل مدیریت",
        callback_data="admin"
    )
])

return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = update.effective_user

text = (
    f"سلام {user.first_name or 'دوست عزیز'} 🌹\n\n"
    "به فروشگاه اینترنتی Mohammadi Fashion خوش آمدید.\n"
    "برای دیدن محصولات از دکمه زیر استفاده کنید."
)

keyboard = main_menu()

if is_admin(user.id):
    keyboard = add_admin_button(keyboard)

await update.message.reply_text(
    text,
    reply_markup=keyboard
)

async def show_products(update, context):
query = update.callback_query
await query.answer()

conn = db()

rows = conn.execute(
    "SELECT * FROM products ORDER BY id DESC"
).fetchall()

conn.close()

if not rows:
    await query.edit_message_text(
        "فعلاً محصولی ثبت نشده است.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )]
        ])
    )
    return

for row in rows:
    caption = (
        f"👗 {row['name']}\n"
        f"💰 قیمت: {row['price']}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🛍 سفارش این محصول",
            callback_data=f"buy:{row['id']}"
        )]
    ])

    if row["photo_id"]:
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=row["photo_id"],
            caption=caption,
            reply_markup=keyboard
        )
    else:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=caption,
            reply_markup=keyboard
        )

await context.bot.send_message(
    chat_id=query.message.chat_id,
    text="برای بازگشت:",
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )]
    ])
)

async def buy_start(update, context):
query = update.callback_query
await query.answer()

product_id = int(query.data.split(":")[1])

conn = db()

row = conn.execute(
    "SELECT * FROM products WHERE id=?",
    (product_id,)
).fetchone()

conn.close()

if not row:
    await query.edit_message_text(
        "این محصول دیگر موجود نیست."
    )
    return ConversationHandler.END

context.user_data["product_id"] = row["id"]
context.user_data["product_name"] = row["name"]
context.user_data["price"] = row["price"]

await query.message.reply_text(
    "لطفاً نام و نام خانوادگی خود را ارسال کنید:"
)

return GET_NAME

async def get_name(update, context):
context.user_data["customer_name"] = update.message.text.strip()

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

p = context.user_data

text = (
    "📦 اطلاعات سفارش\n\n"
    f"👗 محصول: {p['product_name']}\n"
    f"💰 قیمت: {p['price']}\n"
    f"👤 نام: {p['customer_name']}\n"
    f"📞 تماس: {p['phone']}\n\n"
    "آیا سفارش را ثبت کنم؟"
)

keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton(
        "✅ ثبت سفارش",
        callback_data="confirm_order"
    )],
    [InlineKeyboardButton(
        "❌ لغو",
        callback_data="cancel_order"
    )]
])

await update.message.reply_text(
    text,
    reply_markup=keyboard
)

return CONFIRM

async def confirm_order(update, context):
query = update.callback_query
await query.answer()

p = context.user_data

conn = db()

cur = conn.execute(
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
        p["customer_name"],
        p["phone"],
        p["product_id"],
        p["product_name"],
        p["price"]
    )
)

order_id = cur.lastrowid

conn.commit()
conn.close()

await query.edit_message_text(
    f"✅ سفارش شما ثبت شد.\n\n"
    f"شماره سفارش: #{order_id}\n"
    "به‌زودی با شما تماس گرفته می‌شود.",
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )]
    ])
)

if ADMIN_ID:
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "📦 سفارش جدید!\n\n"
            f"شماره: #{order_id}\n"
            f"محصول: {p['product_name']}\n"
            f"قیمت: {p['price']}\n"
            f"نام مشتری: {p['customer_name']}\n"
            f"شماره تماس: {p['phone']}\n"
            f"Telegram ID: {update.effective_user.id}"
        )
    )

context.user_data.clear()

return ConversationHandler.END

async def cancel_order(update, context):
query = update.callback_query
await query.answer()

context.user_data.clear()

await query.edit_message_text(
    "❌ سفارش لغو شد.",
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )]
    ])
)

return ConversationHandler.END

async def my_orders(update, context):
query = update.callback_query
await query.answer()

conn = db()

rows = conn.execute(
    """
    SELECT *
    FROM orders
    WHERE user_id=?
    ORDER BY id DESC
    LIMIT 10
    """,
    (update.effective_user.id,)
).fetchall()

conn.close()

if not rows:
    text = "هنوز سفارشی ثبت نکرده‌اید."
else:
    lines = ["🛒 سفارش‌های شما:\n"]

    for r in rows:
        lines.append(
            f"#{r['id']} — "
            f"{r['product_name']} — "
            f"{r['price']}"
        )

    text = "\n".join(lines)

await query.edit_message_text(
    text,
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )]
    ])
)

async def static_page(update, context, title, body):
query = update.callback_query
await query.answer()

await query.edit_message_text(
    f"{title}\n\n{body}",
    reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )]
    ])
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
    reply_markup=admin_menu()
)

async def admin_add_start(update, context):
query = update.callback_query
await query.answer()

if not is_admin(update.effective_user.id):
    return ConversationHandler.END

await query.message.reply_text(
    "برای افزودن محصول، ابتدا نام محصول را ارسال کنید.\n\n"
    "مثال:\n"
    "بخمل نگین دار"
)

return ADMIN_NAME

async def admin_get_name(update, context):
context.user_data["admin_product_name"] = (
update.message.text.strip()
)

await update.message.reply_text(
    "قیمت محصول را ارسال کنید.\n\n"
    "مثال:\n"
    "۷۰۰"
)

return ADMIN_PRICE

async def admin_get_price(update, context):
context.user_data["admin_product_price"] = (
update.message.text.strip()
)

await update.message.reply_text(
    "حالا عکس محصول را ارسال کنید.\n\n"
    "اگر عکس ندارید، /skip را بفرستید."
)

return ADMIN_PHOTO

async def admin_get_photo(update, context):
if update.message.photo:
context.user_data["admin_photo"] = (
update.message.photo[-1].file_id
)
else:
context.user_data["admin_photo"] = None

return await save_product(update, context)

async def admin_skip_photo(update, context):
context.user_data["admin_photo"] = None
return await save_product(update, context)

async def save_product(update, context):
if not is_admin(update.effective_user.id):
return ConversationHandler.END

name = context.user_data.get(
    "admin_product_name"
)

price = context.user_data.get(
    "admin_product_price"
)

photo = context.user_data.get(
    "admin_photo"
)

conn = db()

conn.execute(
    """
    INSERT INTO products
    (name, price, photo_id)
    VALUES (?, ?, ?)
    """,
    (name, price, photo)
)

conn.commit()
conn.close()

context.user_data.clear()

await update.message.reply_text(
    f"✅ محصول «{name}» "
    f"با قیمت {price} اضافه شد.",
    reply_markup=admin_menu()
)

return ConversationHandler.END

async def admin_delete_start(update, context):
query = update.callback_query
await query.answer()

if not is_admin(update.effective_user.id):
    return

conn = db()

rows = conn.execute(
    "SELECT * FROM products ORDER BY id DESC"
).fetchall()

conn.close()

if not rows:
    await query.edit_message_text(
        "محصولی برای حذف وجود ندارد.",
        reply_markup=admin_menu()
    )
    return

buttons = []

for r in rows:
    buttons.append([
        InlineKeyboardButton(
            f"🗑 {r['name']} — {r['price']}",
            callback_data=f"del:{r['id']}"
        )
    ])

buttons.append([
    InlineKeyboardButton(
        "🔙 مدیریت",
        callback_data="admin"
    )
])

await query.edit_message_text(
    "محصول موردنظر را انتخاب کنید:",
    reply_markup=InlineKeyboardMarkup(buttons)
)

async def admin_delete(update, context):
query = update.callback_query
await query.answer()

if not is_admin(update.effective_user.id):
    return

product_id = int(
    query.data.split(":")[1]
)

conn = db()

conn.execute(
    "DELETE FROM products WHERE id=?",
    (product_id,)
)

conn.commit()
conn.close()

await query.edit_message_text(
    "✅ محصول حذف شد.",
    reply_markup=admin_menu()
)

async def admin_orders(update, context):
query = update.callback_query
await query.answer()

if not is_admin(update.effective_user.id):
    return

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
    text = "هنوز سفارشی ثبت نشده است."
else:
    parts = []

    for r in rows:
        parts.append(
            f"#{r['id']} | "
            f"{r['product_name']} | "
            f"{r['price']}\n"
            f"👤 {r['name']} | "
            f"📞 {r['phone']}"
        )

    text = (
        "📦 آخرین سفارش‌ها:\n\n"
        + "\n\n".join(parts)
    )

await query.edit_message_text(
    text,
    reply_markup=admin_menu()
)

async def button_handler(update, context):
query = update.callback_query
data = query.data

if data == "home":
    await query.answer()

    keyboard = main_menu()

    if is_admin(update.effective_user.id):
        keyboard = add_admin_button(keyboard)

    await query.edit_message_text(
        "🏠 منوی اصلی Mohammadi Fashion",
        reply_markup=keyboard
    )

elif data == "products":
    await show_products(update, context)

elif data.startswith("buy:"):
    await buy_start(update, context)

elif data == "my_orders":
    await my_orders(update, context)

elif data == "contact":
    await static_page(
        update,
        context,
        "📞 تماس با ما",
        "برای سفارش و هماهنگی، "
        "از طریق همین ربات سفارش ثبت کنید."
    )

elif data == "about":
    await static_page(
        update,
        context,
        "ℹ️ درباره فروشگاه",
        "Mohammadi Fashion\n"
        "عرضه‌کننده لباس‌های زنانه."
    )

elif data == "admin":
    await admin_panel(update, context)

elif data == "admin_add":
    await admin_add_start(update, context)

elif data == "admin_delete":
    await admin_delete_start(update, context)

elif data.startswith("del:"):
    await admin_delete(update, context)

elif data == "admin_orders":
    await admin_orders(update, context)

GET_NAME, GET_PHONE, CONFIRM = range(3)

ADMIN_NAME, ADMIN_PRICE, ADMIN_PHOTO = range(3, 6)

async def error_handler(update, context):
logging.error(
"Unhandled error: %s",
context.error
)

def main():
if not TOKEN:
raise RuntimeError(
"BOT_TOKEN environment variable is missing."
)

if ADMIN_ID == 0:
    logging.warning(
        "ADMIN_ID is not set. "
        "Admin notifications will be disabled."
    )

init_db()

threading.Thread(
    target=web_server,
    daemon=True
).start()

application = (
    Application
    .builder()
    .token(TOKEN)
    .build()
)

order_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(
            buy_start,
            pattern=r"^buy:\d+$"
        )
    ],
    states={
        GET_NAME: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_name
            )
        ],
        GET_PHONE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                get_phone
            )
        ],
        CONFIRM: [
            CallbackQueryHandler(
                confirm_order,
                pattern=r"^confirm_order$"
            ),
            CallbackQueryHandler(
                cancel_order,
                pattern=r"^cancel_order$"
            )
        ],
    },
    fallbacks=[
        CommandHandler(
            "cancel",
            cancel_order
        )
    ],
    per_user=True,
    per_chat=True,
    allow_reentry=True,
)

async def admin_cancel(update, context):
    context.user_data.clear()

    await update.message.reply_text(
        "❌ عملیات لغو شد.",
        reply_markup=admin_menu()
    )

    return ConversationHandler.END

admin_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(
            admin_add_start,
            pattern=r"^admin_add$"
        )
    ],
    states={
        ADMIN_NAME: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                admin_get_name
            )
        ],
        ADMIN_PRICE: [
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                admin_get_price
            )
        ],
        ADMIN_PHOTO: [
            MessageHandler(
                filters.PHOTO,
                admin_get_photo
            ),
            CommandHandler(
                "skip",
                admin_skip_photo
            )
        ],
    },
    fallbacks=[
        CommandHandler(
            "cancel",
            admin_cancel
        )
    ],
    per_user=True,
    per_chat=True,
    allow_reentry=True,
)

application.add_handler(
    CommandHandler("start", start)
)

application.add_handler(order_conv)

application.add_handler(admin_conv)

application.add_handler(
    CallbackQueryHandler(button_handler)
)

application.add_error_handler(
    error_handler
)

logging.info("Bot started.")

application.run_polling(
    drop_pending_updates=True
)

if name == "main":
main()
