import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from claude_service import generate_post_text
from social_poster import post_to_facebook, post_to_instagram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_USERS = [
    int(os.getenv("TELEGRAM_CHAT_ID", "0"))
]

# Временное хранилище: chat_id -> {text, photo_bytes}
pending_posts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    await update.message.reply_text(
        "👋 Привет! Отправь мне фото люстры — я создам продающий текст, покажу тебе на проверку, и только после твоего подтверждения опубликую."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.type != "private":
        return
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    await update.message.reply_text("📸 Фото получено! Анализирую и создаю текст...")

    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()

        await update.message.reply_text("✍️ Генерирую продающее описание...")
        post_text = await generate_post_text(bytes(photo_bytes))

        # Сохраняем текст и фото для последующей публикации
        chat_id = update.effective_chat.id
        pending_posts[chat_id] = {
            "text": post_text,
            "photo_bytes": bytes(photo_bytes)
        }

        # Показываем текст и кнопки подтверждения
        keyboard = [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data="confirm_post"),
                InlineKeyboardButton("✏️ Изменить текст", callback_data="edit_post"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_post"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📝 Вот что получилось:\n\n{post_text}\n\n---\nПубликуем?",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if user_id not in ALLOWED_USERS:
        await query.edit_message_text("⛔ У вас нет доступа.")
        return

    if query.data == "confirm_post":
        if chat_id not in pending_posts:
            await query.edit_message_text("❌ Пост не найден. Отправь фото заново.")
            return

        await query.edit_message_text("⏳ Публикую в Facebook и Instagram...")

        post_data = pending_posts.pop(chat_id)
        photo_bytes = post_data["photo_bytes"]
        post_text = post_data["text"]

        fb_result = await post_to_facebook(photo_bytes, post_text)
        ig_result = await post_to_instagram(photo_bytes, post_text)

        message = "✅ Готово!\n\n"
        if fb_result.get("success"):
            message += f"📘 Facebook: {fb_result.get('url', 'опубликовано')}\n"
        else:
            message += f"📘 Facebook: ❌ {fb_result.get('error', 'ошибка')}\n"

        if ig_result.get("success"):
            message += f"📷 Instagram: {ig_result.get('url', 'опубликовано')}\n"
        else:
            message += f"📷 Instagram: ❌ {ig_result.get('error', 'ошибка')}\n"

        await context.bot.send_message(chat_id=chat_id, text=message)

    elif query.data == "edit_post":
        await query.edit_message_text(
            "✏️ Отправь новый текст для поста обычным сообщением — я его сохраню и покажу снова на проверку."
        )
        context.user_data["waiting_for_edit"] = True

    elif query.data == "cancel_post":
        pending_posts.pop(chat_id, None)
        await query.edit_message_text("❌ Публикация отменена.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        return
    if update.effective_chat.type != "private":
        return

    chat_id = update.effective_chat.id

    # Если ждём отредактированный текст
    if context.user_data.get("waiting_for_edit") and chat_id in pending_posts:
        new_text = update.message.text
        pending_posts[chat_id]["text"] = new_text
        context.user_data["waiting_for_edit"] = False

        keyboard = [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data="confirm_post"),
                InlineKeyboardButton("✏️ Изменить текст", callback_data="edit_post"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_post"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📝 Обновлённый текст:\n\n{new_text}\n\n---\nПубликуем?",
            reply_markup=reply_markup
        )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
