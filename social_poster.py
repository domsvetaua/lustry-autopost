import os
import httpx
import tempfile

FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")


async def post_to_facebook(photo_bytes: bytes, text: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Публикуем фото с текстом на Facebook страницу
            response = await client.post(
                f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                data={
                    "message": text,
                    "access_token": FB_PAGE_ACCESS_TOKEN,
                },
                files={
                    "source": ("photo.jpg", photo_bytes, "image/jpeg"),
                }
            )
            result = response.json()

            if "id" in result:
                post_id = result["id"]
                url = f"https://www.facebook.com/{FB_PAGE_ID}/posts/{post_id.split('_')[1]}"
                return {"success": True, "url": url, "id": post_id}
            else:
                error = result.get("error", {}).get("message", str(result))
                return {"success": False, "error": error}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def post_to_instagram(photo_bytes: bytes, text: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # Шаг 1: Загружаем фото через Facebook CDN (нужен публичный URL)
            # Сначала загружаем фото на Facebook и получаем fbid
            upload_response = await client.post(
                f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
                data={
                    "published": "false",
                    "access_token": FB_PAGE_ACCESS_TOKEN,
                },
                files={
                    "source": ("photo.jpg", photo_bytes, "image/jpeg"),
                }
            )
            upload_result = upload_response.json()

            if "id" not in upload_result:
                error = upload_result.get("error", {}).get("message", str(upload_result))
                return {"success": False, "error": f"Ошибка загрузки фото: {error}"}

            # Получаем публичный URL загруженного фото
            photo_id = upload_result["id"]
            url_response = await client.get(
                f"https://graph.facebook.com/v19.0/{photo_id}",
                params={
                    "fields": "images",
                    "access_token": FB_PAGE_ACCESS_TOKEN,
                }
            )
            url_result = url_response.json()
            image_url = url_result.get("images", [{}])[0].get("source")

            if not image_url:
                return {"success": False, "error": "Не удалось получить URL фото"}

            # Шаг 2: Создаём медиа-контейнер в Instagram
            container_response = await client.post(
                f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media",
                data={
                    "image_url": image_url,
                    "caption": text,
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                }
            )
            container_result = container_response.json()

            if "id" not in container_result:
                error = container_result.get("error", {}).get("message", str(container_result))
                return {"success": False, "error": f"Ошибка контейнера: {error}"}

            container_id = container_result["id"]

            # Шаг 3: Публикуем контейнер
            publish_response = await client.post(
                f"https://graph.facebook.com/v19.0/{IG_ACCOUNT_ID}/media_publish",
                data={
                    "creation_id": container_id,
                    "access_token": INSTAGRAM_ACCESS_TOKEN,
                }
            )
            publish_result = publish_response.json()

            if "id" in publish_result:
                ig_post_id = publish_result["id"]
                url = f"https://www.instagram.com/p/{ig_post_id}/"
                return {"success": True, "url": url, "id": ig_post_id}
            else:
                error = publish_result.get("error", {}).get("message", str(publish_result))
                return {"success": False, "error": error}

    except Exception as e:
        return {"success": False, "error": str(e)}
