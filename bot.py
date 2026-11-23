"""Telegram-бот для сайта: каталог, заказы, статус, поддержка, доставка, акции."""
import json
import logging
import os
import re
from pathlib import Path

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO
)
log = logging.getLogger("bot")

# ======================================================================
# НАСТРОЙКИ (Railway -> Variables)
# ======================================================================
TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or 0)  # куда приходят заявки
SITE_URL = os.getenv("SITE_URL", "https://site-197da.firebaseapp.com/")
DATA_FILE = Path(os.getenv("DATA_DIR", ".")) / "orders.json"
CURRENCY = "₸"

# ======================================================================
# ТЕКСТЫ И ДАННЫЕ — ЗАМЕНИТЕ НА СВОИ
# ======================================================================
WELCOME = "Здравствуйте! Я помогу с заказом, доставкой и вопросами. Выберите раздел в меню 👇"

DELIVERY_TEXT = (
    "🚚 Доставка и оплата\n\n"
    "Сроки: 1–3 дня по городу, 3–7 дней по стране.\n"
    "Стоимость: по городу — 1 000 ₸, бесплатно от 20 000 ₸.\n"
    "Зоны доставки: Астана, Алматы, другие города — уточняйте у оператора.\n\n"
    "Оплата: картой на сайте, переводом, наличными курьеру."
)

CONTACTS_TEXT = (
    "📞 Контакты\n\n"
    "Телефон: +7 000 000 00 00\n"
    "Почта: info@example.com\n"
    "Время работы: ежедневно 9:00–21:00"
)

PROMOS_TEXT = "🎁 Акции\n\n• Скидка 10% на первый заказ — промокод WELCOME10\n• Новые предложения появляются здесь."

# Промокоды: код -> скидка в процентах
PROMOS = {"WELCOME10": 10}

FAQ = [
    ("Как оформить заказ?", "Выберите товар в «Каталоге» и нажмите «Заказать» или оформите заказ на сайте."),
    ("Как отменить заказ?", "Напишите оператору до отправки заказа — через «Поддержка»."),
    ("Как вернуть товар?", "Возврат возможен в течение 14 дней. Для оформления обратитесь в поддержку."),
    ("Когда придёт заказ?", "Сроки указаны в «Доставка и оплата». Статус можно проверить по номеру заказа."),
]

SUPPORT_TOPICS = [["Заказ", "Оплата"], ["Доставка", "Другое"]]

# Каталог: категория -> список товаров. photo — ссылка на картинку или None
CATALOG = {
    "Категория 1": [
        {"id": "p1", "name": "Товар 1", "price": 5000, "desc": "Описание товара 1.", "photo": None},
        {"id": "p2", "name": "Товар 2", "price": 7500, "desc": "Описание товара 2.", "photo": None},
    ],
    "Категория 2": [
        {"id": "p3", "name": "Товар 3", "price": 12000, "desc": "Описание товара 3.", "photo": None},
    ],
}
PRODUCTS = {p["id"]: p for items in CATALOG.values() for p in items}

# ======================================================================
# КЛАВИАТУРЫ
# ======================================================================
MENU = [
    ["🛍 Каталог", "🛒 Оформить заказ"],
    ["📦 Статус заказа", "🚚 Доставка и оплата"],
    ["🛟 Поддержка", "❓ Помощь с заказом"],
    ["🎁 Акции", "📞 Контакты"],
]
MENU_KB = ReplyKeyboardMarkup(MENU, resize_keyboard=True)
CANCEL = "❌ Отмена"
CANCEL_KB = ReplyKeyboardMarkup([[CANCEL]], resize_keyboard=True)
MENU_RE = "^(" + "|".join(re.escape(b) for row in MENU for b in row) + ")$"
# Текст, который считается ответом пользователя внутри диалога
TXT = filters.TEXT & ~filters.COMMAND & ~filters.Regex(MENU_RE) & ~filters.Regex(f"^{CANCEL}$")


def site_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("🌐 Открыть сайт", web_app=WebAppInfo(url=SITE_URL))


# ======================================================================
# ХРАНИЛИЩЕ ЗАКАЗОВ (JSON-файл)
# ======================================================================
def load_db() -> dict:
    try:
        return json.loads(DATA_FILE.read_text("utf-8"))
    except Exception:
        return {"last": 0, "orders": {}}


def save_db(db: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=1), "utf-8")


def who(user) -> str:
    uname = f"@{user.username}" if user.username else "без username"
    return f"{user.full_name} ({uname})\nID:{user.id}"


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    if not ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID не задан — уведомление не отправлено")
        return False
    try:
        await context.bot.send_message(ADMIN_CHAT_ID, text)
        return True
    except Exception:
        log.exception("Не удалось отправить сообщение админу")
        return False


# ======================================================================
# ОБЩЕЕ
# ======================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_chat.send_message(WELCOME, reply_markup=MENU_KB)


async def show_menu(update: Update, text: str):
    await update.effective_chat.send_message(text, reply_markup=MENU_KB)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await show_menu(update, "Отменено. Выберите раздел в меню.")
    return ConversationHandler.END


async def start_and_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)
    return ConversationHandler.END


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(f"Chat ID: {update.effective_chat.id}")


# ======================================================================
# ИНФО-РАЗДЕЛЫ
# ======================================================================
async def delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        DELIVERY_TEXT, reply_markup=InlineKeyboardMarkup([[site_button()]])
    )


async def contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [site_button()],
        [InlineKeyboardButton("💬 Написать в поддержку", callback_data="human")],
    ]
    await update.effective_chat.send_message(CONTACTS_TEXT, reply_markup=InlineKeyboardMarkup(kb))


async def promos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(PROMOS_TEXT)


# ----- Помощь с заказом (FAQ) -----
def faq_markup() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(q, callback_data=f"faq:{i}")] for i, (q, _) in enumerate(FAQ)]
    kb.append([InlineKeyboardButton("👤 Связаться с человеком", callback_data="human")])
    return InlineKeyboardMarkup(kb)


async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("Выберите вопрос:", reply_markup=faq_markup())


async def faq_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    question, answer = FAQ[int(q.data.split(":")[1])]
    kb = [
        [InlineKeyboardButton("⬅️ К вопросам", callback_data="faqback")],
        [InlineKeyboardButton("👤 Связаться с человеком", callback_data="human")],
    ]
    await q.edit_message_text(f"{question}\n\n{answer}", reply_markup=InlineKeyboardMarkup(kb))


async def faq_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("Выберите вопрос:", reply_markup=faq_markup())


# ======================================================================
# КАТАЛОГ
# ======================================================================
def categories_markup() -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(name, callback_data=f"cat:{i}")] for i, name in enumerate(CATALOG)]
    kb.append([site_button()])
    return InlineKeyboardMarkup(kb)


async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("Выберите категорию:", reply_markup=categories_markup())


async def catalog_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await catalog(update, context)


async def category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    name = list(CATALOG)[int(q.data.split(":")[1])]
    kb = [
        [InlineKeyboardButton(f"{p['name']} — {p['price']} {CURRENCY}", callback_data=f"prod:{p['id']}")]
        for p in CATALOG[name]
    ]
    kb.append([InlineKeyboardButton("⬅️ Категории", callback_data="catback")])
    await q.edit_message_text(name, reply_markup=InlineKeyboardMarkup(kb))


async def product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = PRODUCTS.get(q.data.split(":", 1)[1])
    if not p:
        return
    text = f"{p['name']}\n{p['price']} {CURRENCY}\n\n{p['desc']}"
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛒 Заказать", callback_data=f"order:{p['id']}")],
            [InlineKeyboardButton("⬅️ Каталог", callback_data="catback")],
        ]
    )
    if p.get("photo"):
        await update.effective_chat.send_photo(p["photo"], caption=text, reply_markup=kb)
    else:
        await update.effective_chat.send_message(text, reply_markup=kb)


# ======================================================================
# ПОДДЕРЖКА: несколько вопросов -> обращение оператору
# ======================================================================
S_TOPIC, S_ORDER, S_TEXT = range(3)


async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data["ticket"] = {}
    kb = ReplyKeyboardMarkup(SUPPORT_TOPICS + [[CANCEL]], resize_keyboard=True)
    await update.effective_chat.send_message("Выберите тему обращения:", reply_markup=kb)
    return S_TOPIC


async def support_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ticket"]["topic"] = update.message.text
    await update.message.reply_text(
        "Номер заказа? Если его нет — отправьте «-».", reply_markup=CANCEL_KB
    )
    return S_ORDER


async def support_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["ticket"]["order"] = update.message.text
    await update.message.reply_text("Опишите проблему одним сообщением.", reply_markup=CANCEL_KB)
    return S_TEXT


async def support_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = context.user_data.pop("ticket", {})
    msg = (
        "🛟 Новое обращение\n"
        f"Тема: {t.get('topic', '-')}\n"
        f"Заказ: {t.get('order', '-')}\n"
        f"От: {who(update.effective_user)}\n\n"
        f"{update.message.text}\n\n"
        "↩️ Ответьте на это сообщение (Reply), и бот перешлёт ответ клиенту."
    )
    ok = await notify_admin(context, msg)
    if ok:
        await show_menu(update, "Спасибо! Обращение передано оператору, ответ придёт сюда в чат.")
    else:
        await show_menu(update, "Не удалось передать обращение. Попробуйте позже или используйте раздел «Контакты».")
    return ConversationHandler.END


async def operator_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оператор отвечает Reply на обращение -> бот пересылает клиенту."""
    m = update.message
    src = m.reply_to_message
    found = re.search(r"ID:(\d+)", (src.text or src.caption or "")) if src else None
    if not found:
        return
    try:
        await context.bot.send_message(int(found.group(1)), f"💬 Ответ оператора:\n\n{m.text}")
        await m.reply_text("✅ Отправлено клиенту")
    except Exception as e:
        await m.reply_text(f"Не удалось отправить: {e}")


# ======================================================================
# СТАТУС ЗАКАЗА
# ======================================================================
ST_NUM = 0


async def status_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("Введите номер заказа:", reply_markup=CANCEL_KB)
    return ST_NUM


async def status_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num = re.sub(r"\D", "", update.message.text)
    o = load_db()["orders"].get(num)
    if not o or o["user_id"] != update.effective_user.id:
        await show_menu(update, "Заказ с таким номером не найден. Проверьте номер или обратитесь в поддержку.")
    else:
        await show_menu(update, f"📦 Заказ №{num}\nСтатус: {o['status']}\nТовар: {o['item']}")
    return ConversationHandler.END


async def set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Для оператора: /setstatus 12 В пути"""
    if len(context.args) < 2:
        await update.message.reply_text("Формат: /setstatus НОМЕР СТАТУС")
        return
    num = context.args[0].lstrip("#")
    status = " ".join(context.args[1:])
    db = load_db()
    o = db["orders"].get(num)
    if not o:
        await update.message.reply_text("Заказ не найден.")
        return
    o["status"] = status
    save_db(db)
    try:
        await context.bot.send_message(o["user_id"], f"📦 Заказ №{num}: {status}")
    except Exception:
        log.exception("Не удалось уведомить клиента")
    await update.message.reply_text(f"✅ Статус заказа №{num} обновлён.")


# ======================================================================
# ОФОРМЛЕНИЕ ЗАКАЗА
# ======================================================================
O_ITEM, O_NAME, O_PHONE, O_ADDR, O_PROMO, O_CONFIRM = range(6)


async def order_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"] = {}
    await update.effective_chat.send_message(
        "Что хотите заказать? Напишите название или выберите товар в «Каталоге».",
        reply_markup=CANCEL_KB,
    )
    return O_ITEM


async def order_from_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    p = PRODUCTS.get(q.data.split(":", 1)[1])
    if not p:
        return ConversationHandler.END
    context.user_data["order"] = {"item": f"{p['name']} — {p['price']} {CURRENCY}"}
    await update.effective_chat.send_message("Как вас зовут?", reply_markup=CANCEL_KB)
    return O_NAME


async def order_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["item"] = update.message.text
    await update.message.reply_text("Как вас зовут?", reply_markup=CANCEL_KB)
    return O_NAME


async def order_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["name"] = update.message.text
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер", request_contact=True)], [CANCEL]],
        resize_keyboard=True,
    )
    await update.message.reply_text("Номер телефона? Можно нажать кнопку или написать вручную.", reply_markup=kb)
    return O_PHONE


async def order_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.message
    context.user_data["order"]["phone"] = m.contact.phone_number if m.contact else m.text
    await m.reply_text("Адрес доставки?", reply_markup=CANCEL_KB)
    return O_ADDR


async def order_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["order"]["address"] = update.message.text
    await update.message.reply_text("Промокод? Если нет — отправьте «-».", reply_markup=CANCEL_KB)
    return O_PROMO


async def order_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    o = context.user_data["order"]
    if code in ("-", "НЕТ"):
        o["promo"] = "нет"
    elif code in PROMOS:
        o["promo"] = f"{code} (−{PROMOS[code]}%)"
    else:
        await update.message.reply_text("Такого промокода нет. Введите другой или отправьте «-».")
        return O_PROMO
    summary = (
        "Проверьте заказ:\n\n"
        f"Товар: {o['item']}\nИмя: {o['name']}\nТелефон: {o['phone']}\n"
        f"Адрес: {o['address']}\nПромокод: {o['promo']}"
    )
    kb = ReplyKeyboardMarkup([["✅ Подтвердить"], [CANCEL]], resize_keyboard=True)
    await update.message.reply_text(summary, reply_markup=kb)
    return O_CONFIRM


async def order_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    o = context.user_data.pop("order", None)
    if not o:
        return await cancel(update, context)
    db = load_db()
    db["last"] += 1
    num = str(db["last"])
    db["orders"][num] = {
        **o,
        "user_id": update.effective_user.id,
        "status": "Принят, ожидает подтверждения",
    }
    save_db(db)
    await notify_admin(
        context,
        f"🛒 Новый заказ №{num}\n"
        f"Товар: {o['item']}\nИмя: {o['name']}\nТелефон: {o['phone']}\n"
        f"Адрес: {o['address']}\nПромокод: {o['promo']}\n"
        f"От: {who(update.effective_user)}\n\n"
        f"Статус клиенту: /setstatus {num} В пути",
    )
    await show_menu(update, f"✅ Заказ №{num} принят! Оператор свяжется с вами. Статус можно проверить в меню.")
    return ConversationHandler.END


async def order_confirm_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажмите «✅ Подтвердить» или «❌ Отмена».")
    return O_CONFIRM


# ======================================================================
async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    log.error("Ошибка в обработчике", exc_info=context.error)


def conv_fallbacks():
    return [
        CommandHandler("cancel", cancel),
        CommandHandler("start", start_and_end),
        MessageHandler(filters.Regex(f"^{CANCEL}$") | filters.Regex(MENU_RE), cancel),
    ]


def main():
    if not TOKEN:
        raise SystemExit("Не задана переменная BOT_TOKEN")

    app = Application.builder().token(TOKEN).build()

    support = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🛟 Поддержка$"), support_start),
            CallbackQueryHandler(support_start, pattern="^human$"),
        ],
        states={
            S_TOPIC: [MessageHandler(TXT, support_topic)],
            S_ORDER: [MessageHandler(TXT, support_order)],
            S_TEXT: [MessageHandler(TXT, support_text)],
        },
        fallbacks=conv_fallbacks(),
    )
    status = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📦 Статус заказа$"), status_start)],
        states={ST_NUM: [MessageHandler(TXT, status_lookup)]},
        fallbacks=conv_fallbacks(),
    )
    order = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🛒 Оформить заказ$"), order_free),
            CallbackQueryHandler(order_from_product, pattern="^order:"),
        ],
        states={
            O_ITEM: [MessageHandler(TXT, order_item)],
            O_NAME: [MessageHandler(TXT, order_name)],
            O_PHONE: [MessageHandler(filters.CONTACT | TXT, order_phone)],
            O_ADDR: [MessageHandler(TXT, order_addr)],
            O_PROMO: [MessageHandler(TXT, order_promo)],
            O_CONFIRM: [
                MessageHandler(filters.Regex("^✅ Подтвердить$"), order_confirm),
                MessageHandler(TXT, order_confirm_retry),
            ],
        },
        fallbacks=conv_fallbacks(),
    )
    app.add_handler(support)
    app.add_handler(status)
    app.add_handler(order)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(MessageHandler(filters.Regex("^🛍 Каталог$"), catalog))
    app.add_handler(MessageHandler(filters.Regex("^🚚 Доставка и оплата$"), delivery))
    app.add_handler(MessageHandler(filters.Regex("^❓ Помощь с заказом$"), help_menu))
    app.add_handler(MessageHandler(filters.Regex("^🎁 Акции$"), promos))
    app.add_handler(MessageHandler(filters.Regex("^📞 Контакты$"), contacts))

    app.add_handler(CallbackQueryHandler(faq_answer, pattern="^faq:"))
    app.add_handler(CallbackQueryHandler(faq_back, pattern="^faqback$"))
    app.add_handler(CallbackQueryHandler(category, pattern="^cat:"))
    app.add_handler(CallbackQueryHandler(catalog_back, pattern="^catback$"))
    app.add_handler(CallbackQueryHandler(product, pattern="^prod:"))

    if ADMIN_CHAT_ID:
        admin = filters.Chat(ADMIN_CHAT_ID)
        app.add_handler(CommandHandler("setstatus", set_status, filters=admin))
        app.add_handler(
            MessageHandler(admin & filters.REPLY & filters.TEXT & ~filters.COMMAND, operator_reply),
            group=1,
        )
    else:
        log.warning("ADMIN_CHAT_ID не задан: заявки и обращения не будут приходить оператору")

    app.add_error_handler(on_error)

    # bootstrap_retries=-1: при flood control бот ждёт и пробует снова, а не падает
    app.run_polling(
        drop_pending_updates=True,
        bootstrap_retries=-1,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
