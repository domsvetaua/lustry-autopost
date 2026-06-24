import logging
import os
from datetime import datetime, timedelta
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from claude_service import generate_post_text
from social_poster import post_to_facebook, post_to_instagram
from token_manager import manual_refresh

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USERS = [int(os.getenv("TELEGRAM_CHAT_ID", "0"))]

user_states = {}
pending_posts = {}

BEST_TIMES = ["18:00", "19:00", "20:00", "21:00"]
KYIV_UTC_OFFSET = 3  # UTC+3

def get_now_kyiv():
    """Поточний час у Харкові (UTC+3)"""
    from datetime import timezone
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=KYIV_UTC_OFFSET)

def get_next_best_time() -> tuple:
    now = get_now_kyiv().replace(tzinfo=None)
    today = now.date()
    for time_str in BEST_TIMES:
        h, m = map(int, time_str.split(":"))
        candidate = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))
        if candidate > now + timedelta(minutes=10):
            return candidate, time_str
    # Всі часи сьогодні минули — беремо перший завтра
    tomorrow = today + timedelta(days=1)
    h, m = map(int, BEST_TIMES[0].split(":"))
    candidate = datetime.combine(tomorrow, datetime.min.time().replace(hour=h, minute=m))
    return candidate, f"завтра в {BEST_TIMES[0]}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    await update.message.reply_text(
        "👋 Привіт! Відправ фото люстри.\n\n"
        "Після фото можеш додати характеристики (матеріал, розмір, ціна) — це покращить опис.\n\n"
        "Я створю окремі тексти для Facebook і Instagram з урахуванням алгоритмів 2026!"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if update.effective_chat.type != "private" or user_id not in ALLOWED_USERS:
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()

    pending_posts[chat_id] = {"photo_bytes": bytes(photo_bytes)}
    user_states[chat_id] = "waiting_characteristics"

    keyboard = [[InlineKeyboardButton("⏭ Пропустити", callback_data="skip_characteristics")]]
    await update.message.reply_text(
        "📸 Фото отримано!\n\n"
        "✍️ Напиши характеристики (необов'язково):\n"
        "_Наприклад: хрусталь, діаметр 60см, 6 ламп, арт-деко, 4500 грн_\n\n"
        "Або натисни Пропустити.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if user_id not in ALLOWED_USERS or update.effective_chat.type != "private":
        return

    state = user_states.get(chat_id)

    if state == "waiting_characteristics":
        user_states[chat_id] = "generating"
        pending_posts[chat_id]["characteristics"] = update.message.text
        await generate_and_show(update, context, chat_id, update.message.text)

    elif state == "waiting_edit_fb":
        pending_posts[chat_id]["fb_text"] = update.message.text
        user_states.pop(chat_id, None)
        await show_fb_preview(context, chat_id, update.message.text)

    elif state == "waiting_edit_ig":
        pending_posts[chat_id]["ig_text"] = update.message.text
        pending_posts[chat_id]["ig_preview"] = update.message.text
        user_states.pop(chat_id, None)
        await show_ig_preview(context, chat_id, update.message.text)


async def generate_and_show(update, context, chat_id, characteristics=""):
    msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Генерую два тексти — для Facebook і Instagram...")
    try:
        photo_bytes = pending_posts[chat_id]["photo_bytes"]
        fb_text, ig_text, fb_preview, ig_preview = await generate_post_text(photo_bytes, characteristics)

        pending_posts[chat_id]["fb_text"] = fb_text
        pending_posts[chat_id]["ig_text"] = ig_text
        pending_posts[chat_id]["ig_preview"] = ig_preview
        user_states.pop(chat_id, None)

        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)

        # Сначала показываем Facebook
        await show_fb_preview(context, chat_id, fb_preview)

    except Exception as e:
        logger.error(f"Помилка: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"❌ Помилка: {str(e)}")


async def show_fb_preview(context, chat_id, fb_text):
    _, time_label = get_next_best_time()
    keyboard = [
        [InlineKeyboardButton("✅ Опублікувати зараз", callback_data="fb_post_now")],
        [InlineKeyboardButton(f"⏰ Запланувати на {time_label}", callback_data="fb_post_scheduled")],
        [InlineKeyboardButton("✏️ Змінити текст", callback_data="fb_edit")],
        [InlineKeyboardButton("❌ Пропустити Facebook", callback_data="fb_skip")],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📘 Текст для Facebook:\n\n{fb_text}\n\n---\nЩо робимо з Facebook?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_ig_preview(context, chat_id, ig_preview):
    _, time_label = get_next_best_time()
    keyboard = [
        [InlineKeyboardButton("✅ Опублікувати зараз", callback_data="ig_post_now")],
        [InlineKeyboardButton(f"⏰ Запланувати на {time_label}", callback_data="ig_post_scheduled")],
        [InlineKeyboardButton("✏️ Змінити текст", callback_data="ig_edit")],
        [InlineKeyboardButton("❌ Пропустити Instagram", callback_data="ig_skip")],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📷 Текст для Instagram:\n\n{ig_preview}\n\n---\nЩо робимо з Instagram?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await query.edit_message_text("⛔ Немає доступу.")
        return

    # Skip characteristics
    if query.data == "skip_characteristics":
        user_states[chat_id] = "generating"
        pending_posts[chat_id]["characteristics"] = ""
        await query.edit_message_text("⏳ Генерую тексти для Facebook і Instagram...")
        await generate_and_show(update, context, chat_id, "")

    # Facebook callbacks
    elif query.data == "fb_post_now":
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✅ Вибрано: опублікувати зараз"
        )
        await publish_facebook(context, chat_id)

    elif query.data == "fb_post_scheduled":
        next_time, time_label = get_next_best_time()
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + f"\n\n---\n⏰ Вибрано: заплановано на {time_label}"
        )
        delay = (next_time - get_now_kyiv().replace(tzinfo=None)).total_seconds()
        asyncio.get_event_loop().call_later(
            delay, lambda: asyncio.ensure_future(publish_facebook_scheduled(context, chat_id))
        )
        # Сразу показываем Instagram
        await show_ig_preview(context, chat_id, pending_posts[chat_id].get("ig_preview", ""))

    elif query.data == "fb_edit":
        keyboard = [
            [InlineKeyboardButton("✏️ Змінити поточний текст", callback_data="fb_edit_manual")],
            [InlineKeyboardButton("🔄 Згенерувати новий", callback_data="fb_edit_regenerate")],
        ]
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✏️ Що хочеш зробити?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "fb_edit_manual":
        user_states[chat_id] = "waiting_edit_fb"
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✏️ Надішли новий текст:"
        )

    elif query.data == "fb_edit_regenerate":
        await query.edit_message_text("🔄 Генерую новий текст для Facebook...")
        try:
            photo_bytes = pending_posts[chat_id]["photo_bytes"]
            chars = pending_posts[chat_id].get("characteristics", "")
            fb_text, ig_text, fb_preview, ig_preview = await generate_post_text(photo_bytes, chars)
            pending_posts[chat_id]["fb_text"] = fb_text
            pending_posts[chat_id]["ig_text"] = ig_text
            pending_posts[chat_id]["ig_preview"] = ig_preview
            await show_fb_preview(context, chat_id, fb_preview)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Помилка: {str(e)}")

    elif query.data == "fb_skip":
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n⏭ Facebook пропущено"
        )
        await show_ig_preview(context, chat_id, pending_posts[chat_id].get("ig_preview", ""))

    # Instagram callbacks
    elif query.data == "ig_post_now":
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✅ Вибрано: опублікувати зараз"
        )
        await publish_instagram(context, chat_id)

    elif query.data == "ig_post_scheduled":
        next_time, time_label = get_next_best_time()
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + f"\n\n---\n⏰ Вибрано: заплановано на {time_label}"
        )
        delay = (next_time - get_now_kyiv().replace(tzinfo=None)).total_seconds()
        asyncio.get_event_loop().call_later(
            delay, lambda: asyncio.ensure_future(publish_instagram_scheduled(context, chat_id))
        )

    elif query.data == "ig_edit":
        keyboard = [
            [InlineKeyboardButton("✏️ Змінити поточний текст", callback_data="ig_edit_manual")],
            [InlineKeyboardButton("🔄 Згенерувати новий", callback_data="ig_edit_regenerate")],
        ]
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✏️ Що хочеш зробити?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "ig_edit_manual":
        user_states[chat_id] = "waiting_edit_ig"
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n✏️ Надішли новий текст:"
        )

    elif query.data == "ig_edit_regenerate":
        await query.edit_message_text("🔄 Генерую новий текст для Instagram...")
        try:
            photo_bytes = pending_posts[chat_id]["photo_bytes"]
            chars = pending_posts[chat_id].get("characteristics", "")
            fb_text, ig_text, fb_preview, ig_preview = await generate_post_text(photo_bytes, chars)
            pending_posts[chat_id]["fb_text"] = fb_text
            pending_posts[chat_id]["ig_text"] = ig_text
            pending_posts[chat_id]["ig_preview"] = ig_preview
            await show_ig_preview(context, chat_id, ig_preview)
        except Exception as e:
            await context.bot.send_message(chat_id=chat_id, text=f"❌ Помилка: {str(e)}")

    elif query.data == "ig_skip":
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() + "\n\n---\n⏭ Instagram пропущено"
        )
        pending_posts.pop(chat_id, None)


async def publish_facebook(context, chat_id):
    if chat_id not in pending_posts:
        await context.bot.send_message(chat_id=chat_id, text="❌ Пост не знайдено. Надішли фото знову.")
        return

    post_data = pending_posts[chat_id]
    result = await post_to_facebook(post_data["photo_bytes"], post_data["fb_text"])

    if result.get("success"):
        await context.bot.send_message(chat_id=chat_id, text=f"📘 Facebook опубліковано!\n{result.get('url', '')}")
    else:
        await context.bot.send_message(chat_id=chat_id, text=f"📘 Facebook: ❌ {result.get('error', 'помилка')}")

    # После Facebook показываем Instagram
    if chat_id in pending_posts:
        await show_ig_preview(context, chat_id, pending_posts[chat_id].get("ig_preview", ""))


async def publish_instagram(context, chat_id):
    if chat_id not in pending_posts:
        await context.bot.send_message(chat_id=chat_id, text="❌ Пост не знайдено. Надішли фото знову.")
        return

    post_data = pending_posts[chat_id]
    result = await post_to_instagram(post_data["photo_bytes"], post_data["ig_text"])

    if result.get("success"):
        await context.bot.send_message(chat_id=chat_id, text=f"📷 Instagram опубліковано!\n{result.get('url', '')}")
    else:
        await context.bot.send_message(chat_id=chat_id, text=f"📷 Instagram: ❌ {result.get('error', 'помилка')}")

    pending_posts.pop(chat_id, None)


async def publish_facebook_scheduled(context, chat_id):
    await context.bot.send_message(chat_id=chat_id, text="⏰ Час прийшов! Публікую Facebook...")
    await publish_facebook(context, chat_id)


async def publish_instagram_scheduled(context, chat_id):
    await context.bot.send_message(chat_id=chat_id, text="⏰ Час прийшов! Публікую Instagram...")
    await publish_instagram(context, chat_id)


async def refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "Використання: /refresh_token ВАШ_USER_TOKEN\n\n"
            "Токен можна отримати на developers.facebook.com/tools/explorer"
        )
        return
    await update.message.reply_text("⏳ Оновлюю токени...")
    success = await manual_refresh(args[0])
    if success:
        await update.message.reply_text("✅ Токени успішно оновлено!")
    else:
        await update.message.reply_text("❌ Не вдалось оновити токени. Перевір правильність токена.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задано!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh_token", refresh_token))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Бот запущено!")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
