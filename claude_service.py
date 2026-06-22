import anthropic
import base64
import os

BRAND_HASHTAGS = {
    "настольная лампа": ("#domsvetalamp", "настольних ламп"),
    "плафонная люстра": ("#domsvetaplaf", "плафонних люстр"),
    "классическая люстра": ("#domsvetaclassic", "класичних люстр"),
    "светодиодная люстра": ("#domsvetaled", "світлодіодних люстр"),
    "торшер": ("#domsvetaторшер", "торшерів"),
    "садовый светильник": ("#domsvetadvor", "садово-паркових світильників"),
    "лофт": ("#domsvetaloft", "світильників у стилі лофт"),
}

async def generate_post_text(photo_bytes: bytes, characteristics: str = "") -> tuple:
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
                    "text": f"""Ти — професійний копірайтер для інтернет-магазину люстр "Дом Света" (Харків, Україна).

Подивись на фото і виконай два завдання:

=== ЗАВДАННЯ 1: КАТЕГОРІЯ ===
Визнач категорію з списку (вибери одну):
{categories}

=== ЗАВДАННЯ 2: ПОСТ ===
{char_block}

ПРАВИЛА INSTAGRAM 2026:

1. СТРУКТУРА:
   - Рядки 1-2: яскравий гачок з емодзі (видно до "читати далі")
   - Основна частина: опис, матеріал, стиль, переваги, для яких інтер'єрів
   - SEO-ключові слова природно в тексті
   - Передостанній абзац ОБОВ'ЯЗКОВО: "Більше [назва категорії] знайдете у нас на сайті за посиланням у шапці профілю або за хештегом [BRAND_HASHTAG]"
   - Довжина: 150-250 слів

2. ХЕШТЕГИ (рівно 4 — після тексту, окремим рядком):
   - 1 широкий: #люстра або #світильник
   - 2 нішевих: стиль/матеріал
   - 1 локальний: #харків
   - НЕ додавай брендовий хештег у блок хештегів — він вже є в тексті!

=== ФОРМАТ ВІДПОВІДІ ===
КАТЕГОРІЯ: [категорія]

ТЕКСТ ПОСТА:
[повний текст з хештегами в кінці]

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
        if line.startswith("КАТЕГОРІЯ:") or line.startswith("КАТЕГОРИЯ:"):
            category = line.split(":", 1)[1].strip().lower()
        elif line.startswith("ТЕКСТ ПОСТА:") or line.startswith("ТЕКСТ ПОСТУ:"):
            mode = "post"
        elif line.startswith("ГЕОТЕГ:"):
            mode = None
            geotag = line.replace("ГЕОТЕГ:", "").strip()
        elif mode == "post":
            post_text += line + "\n"

    post_text = post_text.strip()

    # Подставляем брендовый хештег в текст
    for key, (hashtag, category_name) in BRAND_HASHTAGS.items():
        if key in category:
            post_text = post_text.replace("[BRAND_HASHTAG]", hashtag)
            # Если Claude не вставил хештег в текст — добавляем принудительно
            if hashtag not in post_text:
                # Ищем фразу про сайт и добавляем хештег после неё
                phrases = ["за хештегом", "за хэштегом"]
                for phrase in phrases:
                    if phrase in post_text:
                        idx = post_text.find(phrase) + len(phrase)
                        post_text = post_text[:idx] + f" {hashtag}" + post_text[idx:]
                        break
                else:
                    post_text += f"\n{hashtag}"
            break

    post_for_publishing = post_text
    post_for_preview = post_text
    if geotag:
        post_for_preview += f"\n\n📍 Геотег для ручного добавления: {geotag}"

    return post_for_publishing, post_for_preview
