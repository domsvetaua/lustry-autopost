import os
import httpx
from token_manager import get_fb_token, get_ig_token

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")


async def post_to_facebook(photo_bytes: bytes, text: str) -> dict:
    try:
        token = await get_fb_token()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                data={"message": text, "access_token": token},
                files={"source": ("photo.jpg", photo_bytes, "image/jpeg")}
            )
            result = response.json()
            if "id" in result:
                post_id = result["id"]
                page_post_id = post_id.split("_")[1] if "_" in post_id else post_id
                return {"success": True, "url": f"https://www.facebook.com/{FB_PAGE_ID}/posts/{page_post_id}"}
            else:
                error = result.get("error", {}).get("message", str(result))
                return {"success": False, "error": error}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def post_to_instagram(photo_bytes: bytes, text: str) -> dict:
    try:
        fb_token = await get_fb_token()
        ig_token = await get_ig_token()

        async with httpx.AsyncClient(timeout=60) as client:
            # Шаг 1: Загружаем фото на Facebook как неопубликованное
            upload_response = await client.post(
                f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                data={"published": "false", "temporary": "true", "access_token": fb_token},
                files={"source": ("photo.jpg", photo_bytes, "image/jpeg")}
            )
            upload_result = upload_response.json()
            if "id" not in upload_result:
                error = upload_result.get("error", {}).get("message", str(upload_result))
                return {"success": False, "error": f"Ошибка загрузки фото: {error}"}

            photo_id = upload_result["id"]

            # Шаг 2: Получаем URL фото
            url_response = await client.get(
                f"https://graph.facebook.com/v19.0/{photo_id}",
                params={"fields": "images", "access_token": fb_token}
            )
            images = url_response.json().get("images", [])
            if not images:
                return {"success": False, "error": "Не удалось получить URL фото"}
            image_url = images[0].get("source")

            # Шаг 3: Создаём контейнер в Instagram
            container_response = await client.post(
                f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
                data={"image_url": image_url, "caption": text, "access_token": ig_token}
            )
            container_result = container_response.json()
            if "id" not in container_result:
                error = container_result.get("error", {}).get("message", str(container_result))
                return {"success": False, "error": f"Ошибка контейнера IG: {error}"}

            # Шаг 4: Публикуем
            publish_response = await client.post(
                f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish",
                data={"creation_id": container_result["id"], "access_token": ig_token}
            )
            publish_result = publish_response.json()
            if "id" in publish_result:
                return {"success": True, "url": f"https://www.instagram.com/p/{publish_result['id']}/"}
            else:
                error = publish_result.get("error", {}).get("message", str(publish_result))
                return {"success": False, "error": error}

    except Exception as e:
        return {"success": False, "error": str(e)}
