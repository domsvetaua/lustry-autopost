import os
import httpx
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Храним токены в памяти
_tokens = {
    "fb_page_token": os.getenv("FB_PAGE_ACCESS_TOKEN", ""),
    "ig_token": os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
    "last_refresh": None
}

APP_ID = "1854955815157050"
APP_SECRET = os.getenv("FB_APP_SECRET", "")
PAGE_ID = os.getenv("FB_PAGE_ID", "100654001590699")


async def get_fb_token() -> str:
    """Возвращает актуальный FB Page Token, обновляет если нужно"""
    await _refresh_if_needed()
    return _tokens["fb_page_token"]


async def get_ig_token() -> str:
    """Возвращает актуальный Instagram Token"""
    await _refresh_if_needed()
    return _tokens["ig_token"]


async def _refresh_if_needed():
    """Обновляет токены если прошло больше 50 дней"""
    last = _tokens.get("last_refresh")
    if last and datetime.now() - last < timedelta(days=50):
        return  # Ещё свежие

    await _refresh_tokens()


async def _refresh_tokens():
    """Обменивает токены на новые долгоживущие"""
    if not APP_SECRET:
        logger.warning("FB_APP_SECRET не задан — автообновление токенов недоступно")
        return

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Шаг 1: Обновляем FB Page Token через long-lived exchange
            current_token = _tokens["fb_page_token"]

            exchange_resp = await client.get(
                "https://graph.facebook.com/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": APP_ID,
                    "client_secret": APP_SECRET,
                    "fb_exchange_token": current_token,
                }
            )
            exchange_result = exchange_resp.json()

            if "access_token" in exchange_result:
                long_lived_token = exchange_result["access_token"]

                # Шаг 2: Получаем Page Token из долгоживущего токена
                page_resp = await client.get(
                    f"https://graph.facebook.com/v19.0/{PAGE_ID}",
                    params={
                        "fields": "access_token",
                        "access_token": long_lived_token,
                    }
                )
                page_result = page_resp.json()

                if "access_token" in page_result:
                    _tokens["fb_page_token"] = page_result["access_token"]
                    _tokens["ig_token"] = page_result["access_token"]
                    _tokens["last_refresh"] = datetime.now()
                    logger.info("✅ Токены Facebook/Instagram успешно обновлены")
                else:
                    logger.error(f"Ошибка получения Page Token: {page_result}")
            else:
                logger.error(f"Ошибка обмена токена: {exchange_result}")

    except Exception as e:
        logger.error(f"Ошибка обновления токенов: {e}")


async def notify_token_error(context, chat_id: int, error: str):
    """Отправляет уведомление в Telegram если токен слетел"""
    if "Session has expired" in error or "Invalid OAuth" in error or "Cannot parse" in error:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Токен Facebook/Instagram слетел!\n\n"
                 "Открой developers.facebook.com/tools/explorer → скопируй User Token → "
                 "отправь боту команду /refresh_token ТОКЕН"
        )


async def manual_refresh(new_user_token: str) -> bool:
    """Ручное обновление токена через новый User Token"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            page_resp = await client.get(
                f"https://graph.facebook.com/v19.0/{PAGE_ID}",
                params={
                    "fields": "access_token",
                    "access_token": new_user_token,
                }
            )
            result = page_resp.json()

            if "access_token" in result:
                _tokens["fb_page_token"] = result["access_token"]
                _tokens["ig_token"] = result["access_token"]
                _tokens["last_refresh"] = datetime.now()
                return True
            return False
    except Exception as e:
        logger.error(f"Ошибка ручного обновления: {e}")
        return False
