import logging
import os
from datetime import datetime, timedelta
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from claude_service import generate_post_text
from social_poster import post_to_facebook, post_to_instagram
from token_manager import manual_refresh, notify_token_error

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USERS = [int(os.getenv("TELEGRAM_CHAT_ID", "0"))]

user_states = {}
pending_posts = {}

BEST_TIMES = ["18:00", "19:00", "20:00", "21:00"]

def get_next_best_time() -> tuple:
    now = datetime.now()
    today = now.date()
    for time_str in BEST_TIMES:
        h, m = map(int, time_str.split(":"))
        candidate = datetime.combine(today, datetime.min.time().replace(hour=h, minute=m))
        if candidate > now + timedelta(minutes=5):
            return candidate, time_str
    tomorrow = today + timedelta(days=1)
    h, m = map(int, BEST_TIMES[0].split(":"))
    candidate = datetime.combine(tomorrow, datetime.min.time().replace(hour=h, minute=m))
    return candidate, f"завтра в {BEST_TIMES[0]}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    await update.message.reply_text(
        "👋 Привет! Отправь фото люстры.\n\n"
        "После фото можешь добавить характеристики (материал, размер, цена) — это улучшит описание.\n\n"
        "Я создам текст по правилам Instagram 2026 и покажу на проверку перед публикацией."
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

    keyboard = [[InlineKeyboardButton("⏭ Пропустить", callback_data="skip_characteristics")]]
    await update.message.reply_text(
        "📸 Фото получено!\n\n"
        "✍️ Напиши характеристики (необязательно):\n"
        "_Например: хрусталь, диаметр 60см, 6 ламп, арт-деко, 4500 грн_\n\n"
        "Или нажми Пропустить.",
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
        await generate_and_show(update, context, chat_id, update.message.text)

    elif state == "waiting_edit":
        new_text = update.message.text
        pending_posts[chat_id]["post_for_publishing"] = new_text
        pending_posts[chat_id]["post_for_preview"] = new_text
        user_states.pop(chat_id, None)
        await show_preview(context, chat_id, new_text)


async def generate_and_show(update, context, chat_id, characteristics=""):
    msg = await context.bot.send_message(chat_id=chat_id, text="⏳ Анализирую фото и генерирую текст...")
    try:
        photo_bytes = pending_posts[chat_id]["photo_bytes"]
        post_for_publishing, post_for_preview = await generate_post_text(photo_bytes, characteristics)

        pending_posts[chat_id]["post_for_publishing"] = post_for_publishing
        pending_posts[chat_id]["post_for_preview"] = post_for_preview
        user_states.pop(chat_id, None)

        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
        await show_preview(context, chat_id, post_for_preview)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f"❌ Ошибка: {str(e)}")


async def show_preview(context, chat_id, preview_text):
    _, time_label = get_next_best_time()
    keyboard = [
        [InlineKeyboardButton("✅ Публиковать сейчас", callback_data="post_now")],
        [InlineKeyboardButton(f"⏰ Запланировать на {time_label}", callback_data="post_scheduled")],
        [InlineKeyboardButton("✏️ Изменить текст", callback_data="edit_post")],
        [InlineKeyboardButton("❌ Отменить", callback_data="cancel_post")],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📝 *Готовый пост:*\n\n{preview_text}\n\n---\nЧто делаем?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await query.edit_message_reply_markup(reply_markup=None)
        await context.bot.send_message(chat_id=chat_id, text="⛔ Нет доступа.")
        return

    if query.data == "skip_characteristics":
        user_states[chat_id] = "generating"
        await query.edit_message_text("⏭ Характеристики пропущены. Генерирую текст на основе фото...")
        await generate_and_show(update, context, chat_id, "")

    elif query.data == "post_now":
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() +
            "\n\n---\n✅ Выбрано: *Публиковать сейчас*",
            parse_mode="Markdown"
        )
        await publish_post(context, chat_id)

    elif query.data == "post_scheduled":
        next_time, time_label = get_next_best_time()
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() +
            f"\n\n---\n⏰ Выбрано: *Запланировано на {time_label}*",
            parse_mode="Markdown"
        )
        delay = (next_time - datetime.now()).total_seconds()
        asyncio.get_event_loop().call_later(
            delay,
            lambda: asyncio.ensure_future(publish_scheduled(context, chat_id))
        )

    elif query.data == "edit_post":
        user_states[chat_id] = "waiting_edit"
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() +
            "\n\n---\n✏️ Выбрано: *Изменить текст*\n\nНапиши новый текст:",
            parse_mode="Markdown"
        )

    elif query.data == "cancel_post":
        pending_posts.pop(chat_id, None)
        user_states.pop(chat_id, None)
        await query.edit_message_text(
            query.message.text.split("---")[0].strip() +
            "\n\n---\n❌ Выбрано: *Отменено*",
            parse_mode="Markdown"
        )


async def publish_post(context, chat_id):
    if chat_id not in pending_posts:
        await context.bot.send_message(chat_id=chat_id, text="❌ Пост не найден. Отправь фото заново.")
        return

    post_data = pending_posts.pop(chat_id)
    photo_bytes = post_data["photo_bytes"]
    post_text = post_data["post_for_publishing"]  # без геотега

    fb_result = await post_to_facebook(photo_bytes, post_text)
    ig_result = await post_to_instagram(photo_bytes, post_text)

    fb_status = f"✅ {fb_result.get('url', 'опубликовано')}" if fb_result.get('success') else f"❌ {fb_result.get('error', 'ошибка')}"
    ig_status = f"✅ {ig_result.get('url', 'опубликовано')}" if ig_result.get('success') else f"❌ {ig_result.get('error', 'ошибка')}"

    message = f"✅ Опубликовано!\n\n📘 Facebook: {fb_status}\n📷 Instagram: {ig_status}"

    await context.bot.send_message(chat_id=chat_id, text=message)


async def publish_scheduled(context, chat_id):
    await context.bot.send_message(chat_id=chat_id, text="⏰ Время пришло! Публикую запланированный пост...")
    await publish_post(context, chat_id)


async def refresh_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование: /refresh_token ВАШ_USER_TOKEN\n\n"
            "Токен можно получить на developers.facebook.com/tools/explorer"
        )
        return

    new_token = args[0]
    await update.message.reply_text("⏳ Обновляю токены...")
    success = await manual_refresh(new_token)
    if success:
        await update.message.reply_text("✅ Токены успешно обновлены! Теперь можно постить.")
    else:
        await update.message.reply_text("❌ Не удалось обновить токены. Проверь правильность токена.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh_token", refresh_token))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Бот запущен!")
    app.run_polling(
        drop_pending_updates=True,  # игнорируем накопившиеся апдейты при старте
        allowed_updates=Update.ALL_TYPES,
    )

if __name__ == "__main__":
    main()
# Этот блок заменяет функцию main() — скопируй весь файл целиком
