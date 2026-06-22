import logging
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from claude_service import generate_post_text
from social_poster import post_to_facebook, post_to_instagram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Белый список разрешённых пользователей
ALLOWED_USERS = [
    int(os.getenv("TELEGRAM_CHAT_ID", "0"))
    # Добавь сюда ID доверенных людей через запятую, например:
    # 123456789,
    # 987654321,
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    await update.message.reply_text(
        "👋 Привет! Отправь мне фото люстры — я создам продающий текст и опубликую его в Facebook и Instagram."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка доступа
    user_id = update.effective_user.id
    if update.effective_chat.type != "private":
        return
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return

    await update.message.reply_text("📸 Фото получено! Анализирую и создаю текст...")

    try:
        # Получаем фото в максимальном качестве
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = await file.download_as_bytearray()

        # Генерируем текст через Claude
        await update.message.reply_text("✍️ Генерирую продающее описание...")
        post_text = await generate_post_text(bytes(photo_bytes))

        await update.message.reply_text(f"📝 Текст готов:\n\n{post_text}\n\n⏳ Публикую в соцсети...")

        # Публикуем в Facebook
        fb_result = await post_to_facebook(bytes(photo_bytes), post_text)
        
        # Публикуем в Instagram
        ig_result = await post_to_instagram(bytes(photo_bytes), post_text)

        # Отправляем уведомление об успехе
        message = "✅ Опубликовано!\n\n"
        if fb_result.get("success"):
            message += f"📘 Facebook: {fb_result.get('url', 'нет ссылки')}\n"
        else:
            message += f"📘 Facebook: ❌ {fb_result.get('error', 'ошибка')}\n"

        if ig_result.get("success"):
            message += f"📷 Instagram: {ig_result.get('url', 'нет ссылки')}\n"
        else:
            message += f"📷 Instagram: ❌ {ig_result.get('error', 'ошибка')}\n"

        await update.message.reply_text(message)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан!")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
