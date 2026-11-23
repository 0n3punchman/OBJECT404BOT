"""Simple Telegram support bot for a small business website."""

import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
DELIVERY_TEXT = os.environ.get(
    "DELIVERY_TEXT",
    "Напишите сюда условия доставки: сроки, стоимость и доступные города.",
)
CONTACT_TEXT = os.environ.get("CONTACT_TEXT", "Добавьте сюда телефон, адрес или часы работы.")
SITE_URL = os.environ.get("SITE_URL", "https://site-197da.firebaseapp.com/")

MENU = InlineKeyboardMarkup(
    [
        [InlineKeyboardButton("💬 Поддержка", callback_data="support")],
        [InlineKeyboardButton("🚚 Доставка", callback_data="delivery")],
        [InlineKeyboardButton("📍 Контакты", callback_data="contacts")],
        [InlineKeyboardButton("🌐 Открыть сайт", url=SITE_URL)],
    ]
)

# In-memory support states and reply links. These reset when the bot restarts.
waiting_for_support: set[int] = set()
admin_message_to_user: dict[int, int] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Здравствуйте! Чем могу помочь? Выберите раздел:", reply_markup=MENU
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text("Выберите раздел:", reply_markup=MENU)


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        f"Ваш Telegram ID: {update.effective_user.id}"
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "support":
        user_id = query.from_user.id
        waiting_for_support.add(user_id)
        await query.message.reply_text(
            "Напишите одним сообщением, с чем нужна помощь. Я передам обращение оператору."
        )
    elif query.data == "delivery":
        await query.message.reply_text(DELIVERY_TEXT, reply_markup=MENU)
    elif query.data == "contacts":
        await query.message.reply_text(CONTACT_TEXT, reply_markup=MENU)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return

    # An operator can reply to the bot's copied support message in the admin chat.
    if (
        ADMIN_CHAT_ID
        and str(message.chat_id) == ADMIN_CHAT_ID
        and message.reply_to_message
        and message.reply_to_message.message_id in admin_message_to_user
    ):
        customer_id = admin_message_to_user[message.reply_to_message.message_id]
        await context.bot.copy_message(
            chat_id=customer_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        await message.reply_text("Ответ отправлен клиенту.")
        return

    if user.id not in waiting_for_support:
        await message.reply_text("Выберите раздел в меню:", reply_markup=MENU)
        return

    waiting_for_support.discard(user.id)
    if not ADMIN_CHAT_ID:
        await message.reply_text(
            "Обращение не отправлено: владелец ещё не настроил ADMIN_CHAT_ID."
        )
        log.warning("Support message received but ADMIN_CHAT_ID is not configured")
        return

    username = f"@{user.username}" if user.username else "без username"
    heading = (
        f"Обращение в поддержку\n"
        f"От: {user.full_name} ({username})\n"
        f"Telegram ID: {user.id}\n\n"
        "Ответьте на скопированное ниже сообщение, чтобы написать клиенту."
    )
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=heading)
    copied = await context.bot.copy_message(
        chat_id=ADMIN_CHAT_ID,
        from_chat_id=message.chat_id,
        message_id=message.message_id,
    )
    admin_message_to_user[copied.message_id] = message.chat_id
    await message.reply_text("Спасибо! Передал сообщение оператору.", reply_markup=MENU)


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Set BOT_TOKEN in the environment before starting the bot.")
    app: Application = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler(["start", "help", "menu"], start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
