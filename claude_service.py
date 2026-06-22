import anthropic
import base64
import os

BRAND_HASHTAGS = {
    "настольная лампа": ("#domsvetalamp", "настольных ламп"),
    "плафонная люстра": ("#domsvetaplaf", "плафонных люстр"),
    "классическая люстра": ("#domsvetaclassic", "классических люстр"),
    "светодиодная люстра": ("#domsvetaled", "светодиодных люстр"),
    "торшер": ("#domsvetaторшер", "торшеров"),
    "садовый светильник": ("#domsvetadvor", "садово-парковых светильников"),
    "лофт": ("#domsvetaloft", "светильников в стиле лофт"),
}

async def generate_post_text(photo_bytes: bytes, characteristics: str = "") -> tuple[str, str]:
    """Возвращает (текст_для_поста, текст_с_геотегом_для_превью)"""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    char_block = ""
    if characteristics:
        char_block = f"""
Дополнительные характеристики от продавца:
{characteristics}
Обязательно используй эти характеристики в описании.
"""

    categories = "\n".join([f'- "{k}"' for k in BRAND_HASHTAGS.keys()])

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                },
                {
                    "type": "text",
                    "text": f"""Ты — профессиональный копирайтер для интернет-магазина люстр "Дом Света" (Харьков, Украина).

Посмотри на фото и выполни два задания:

=== ЗАДАНИЕ 1: КАТЕГОРИЯ ===
Определи категорию из списка (выбери одну):
{categories}

=== ЗАДАНИЕ 2: ПОСТ ===
{char_block}

ПРАВИЛА INSTAGRAM 2026:

1. СТРУКТУРА:
   - Строки 1-2: яркий крючок с эмодзи (видно до "читать далее")
   - Основная часть: описание, материал, стиль, преимущества, для каких интерьеров
   - SEO-ключевые слова естественно в тексте
   - Предпоследняя строка: "Більше [название категории] знайдете у нас на сайті за посиланням у шапці профілю або за хештегом [BRAND_HASHTAG]"
   - Длина: 150-250 слов

2. ХЕШТЕГИ (ровно 5 — жёсткий лимит 2026!):
   - 1 широкий: #люстра или #світильник
   - 2 нишевых: стиль/материал (русский + английский)
   - 1 локальный: #харків
   - 1 брендовый: [BRAND_HASHTAG]

=== ФОРМАТ ОТВЕТА ===
КАТЕГОРИЯ: [категория]

ТЕКСТ ПОСТА:
[полный текст с хештегами]

ГЕОТЕГ: Харків / Kharkiv, Ukraine"""
                }
            ],
        }],
    )

    raw = message.content[0].text
    category = ""
    post_text = ""
    geotag = ""
    mode = None

    for line in raw.strip().split("\n"):
        if line.startswith("КАТЕГОРИЯ:"):
            category = line.replace("КАТЕГОРИЯ:", "").strip().lower()
        elif line.startswith("ТЕКСТ ПОСТА:"):
            mode = "post"
        elif line.startswith("ГЕОТЕГ:"):
            mode = None
            geotag = line.replace("ГЕОТЕГ:", "").strip()
        elif mode == "post":
            post_text += line + "\n"

    post_text = post_text.strip()

    # Подставляем брендовый хештег
    brand_hashtag = ""
    for key, (hashtag, category_name) in BRAND_HASHTAGS.items():
        if key in category:
            brand_hashtag = hashtag
            post_text = post_text.replace("[BRAND_HASHTAG]", hashtag)
            if hashtag not in post_text:
                post_text += f"\n{hashtag}"
            break

    # Текст для публикации — без геотега
    post_for_publishing = post_text

    # Текст для превью — с геотегом
    post_for_preview = post_text
    if geotag:
        post_for_preview += f"\n\n📍 Геотег для ручного добавления: {geotag}"

    return post_for_publishing, post_for_preview
