import anthropic
import base64
import os
import re
import logging

logger = logging.getLogger(__name__)

# Async-клієнт створюємо один раз на рівні модуля
client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

BRAND_HASHTAGS = {
    "настольная лампа": ("#domsvetalamp", "настільних ламп"),
    "плафонная люстра": ("#domsvetaplaf", "плафонних люстр"),
    "классическая люстра": ("#domsvetaclassic", "класичних люстр"),
    "светодиодная люстра": ("#domsvetaled", "світлодіодних люстр"),
    "торшер": ("#domsvetaторшер", "торшерів"),
    "садовый светильник": ("#domsvetadvor", "садово-паркових світильників"),
    "лофт": ("#domsvetaloft", "світильників у стилі лофт"),
}

async def generate_post_text(photo_bytes: bytes, characteristics: str = "") -> tuple:
    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    char_block = ""
    if characteristics:
        char_block = f"""
Додаткові характеристики від продавця:
{characteristics}
Обов'язково використай ці характеристики в описі.
"""

    categories = "\n".join([f'- "{k}"' for k in BRAND_HASHTAGS.keys()])

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data},
                    },
                    {
                        "type": "text",
                        "text": f"""Ти — професійний копірайтер магазину люстр "Дом Света" (Харків, Україна).

Подивись на фото і виконай завдання:

=== КРОК 1: КАТЕГОРІЯ ===
Визнач категорію з списку (вибери одну):
{categories}
{char_block}

=== КРОК 2: ПОСТ ДЛЯ FACEBOOK ===

Правила Facebook 2026:
- Рядки 1-2: крючок з емодзі — питання або факт (видно до "читати далі")
- Рядки 3-8: опис товару, SEO-ключові слова природно в тексті
- Рядки 9-10: переваги + CTA ("Напиши в повідомлення")
- Передостанній рядок: питання для коментарів (генерує залученість)
- Останній рядок: ОБОВ'ЯЗКОВО напиши повністю: "Більше [назва категорії] знайдете на нашій сторінці — посилання на сайт у розділі 'Про нас'."
- ЗАБОРОНЕНО: жодних хештегів, жодного слова "хештег", жодного слова "безкоштовно"
- Довжина: 100-150 слів

=== КРОК 3: ПОСТ ДЛЯ INSTAGRAM ===

Правила Instagram 2026:
- Рядки 1-2: крючок з емодзі — інший ніж у Facebook, більш візуальний
- Рядки 3-7: образний опис товару, SEO-ключові слова природно в тексті
- Рядок 8: питання для коментарів — особисте і конкретне
- Рядок 9: CTA з посиланням у шапці профілю
- Рядок 10: ОБОВ'ЯЗКОВО напиши точно: "Більше [назва категорії] у нас на сайті за посиланням у шапці профілю або за хештегом [BRAND_HASHTAG]" — тільки [BRAND_HASHTAG], більше нічого в цьому рядку!
- Порожній рядок
- Останній рядок: 4-5 хештегів на основі характеристик товару (матеріал, стиль, тип) — БЕЗ будь-яких брендових тегів!
- ЗАБОРОНЕНО: слово "безкоштовно", брендові теги в блоці хештегів
- Довжина: 150-200 слів

=== ФОРМАТ ВІДПОВІДІ ===
КАТЕГОРІЯ: [категорія]

FACEBOOK:
[текст поста для Facebook]

INSTAGRAM:
[текст поста для Instagram]

ГЕОТЕГ: Харків / Kharkiv, Ukraine"""
                    }
                ],
            }],
        )
    except Exception as e:
        logger.error(f"Помилка виклику Anthropic API: {e}", exc_info=True)
        raise RuntimeError(f"Не вдалося згенерувати текст: {e}")

    raw = message.content[0].text
    logger.info(f"Claude raw: {raw[:300]}")

    category = ""
    fb_text = ""
    ig_text = ""
    geotag = ""
    mode = None

    for line in raw.strip().split("\n"):
        l = line.strip()
        if l.startswith("КАТЕГОРІЯ:") or l.startswith("КАТЕГОРИЯ:"):
            category = l.split(":", 1)[1].strip().lower()
            mode = None
        elif l.startswith("FACEBOOK:"):
            mode = "fb"
        elif l.startswith("INSTAGRAM:"):
            mode = "ig"
        elif l.startswith("ГЕОТЕГ:"):
            geotag = l.replace("ГЕОТЕГ:", "").strip()
            mode = None
        elif mode == "fb":
            fb_text += line + "\n"
        elif mode == "ig":
            ig_text += line + "\n"

    fb_text = fb_text.strip()
    ig_text = ig_text.strip()

    # Знаходимо брендовий хештег
    brand_hashtag = ""
    category_name = ""
    for key, (hashtag, cat_name) in BRAND_HASHTAGS.items():
        if key in category:
            brand_hashtag = hashtag
            category_name = cat_name
            break

    # === ЧИСТИМО FACEBOOK ===
    fb_lines = fb_text.strip().split("\n")
    clean_fb = []
    for line in fb_lines:
        # Видаляємо рядки що починаються з хештегу
        if line.strip().startswith("#"):
            continue
        # Видаляємо хештеги з середини рядків
        words = line.split()
        words = [w for w in words if not w.startswith("#")]
        clean_line = " ".join(words).strip()
        # Видаляємо обірвані фрази про хештег
        clean_line = re.sub(r'\s*(або за хештегом|за хештегом)\s*\S*\s*$', '', clean_line).strip()
        clean_line = re.sub(r'\s*(або за хештегом|за хештегом)\s*$', '', clean_line).strip()
        if clean_line:
            clean_fb.append(clean_line)
    fb_text = "\n".join(clean_fb).strip()

    # === ЧИСТИМО INSTAGRAM ===
    ig_text = ig_text.replace("[BRAND_HASHTAG]", brand_hashtag)

    def is_brand_tag(tag: str) -> bool:
        t = tag.lower().lstrip("#")
        brand_words = ["дом", "dom", "свет", "svet", "sveta"]
        return any(w in t for w in brand_words)

    ig_lines = ig_text.strip().split("\n")
    clean_ig = []
    for line in ig_lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # З блоку хештегів прибираємо всі брендові теги
            tags = stripped.split()
            clean_tags = [t for t in tags if not is_brand_tag(t)]
            if clean_tags:
                clean_ig.append(" ".join(clean_tags))
        else:
            # З тексту прибираємо брендові теги крім дозволеного
            words = line.split()
            clean_words = []
            for w in words:
                if w.startswith("#") and is_brand_tag(w) and w.lower() != brand_hashtag.lower():
                    continue
                clean_words.append(w)
            clean_ig.append(" ".join(clean_words))
    ig_text = "\n".join(clean_ig).strip()

    # Завжди вставляємо брендовий хештег після "за хештегом"
    if brand_hashtag and "за хештегом" in ig_text:
        ig_text = re.sub(r"за хештегом\s*#?\S*", f"за хештегом {brand_hashtag}", ig_text, count=1)

    # Превью для Instagram з геотегом
    ig_preview = ig_text
    if geotag:
        ig_preview += f"\n\n📍 Геотег для ручного додавання: {geotag}"

    return fb_text, ig_text, fb_text, ig_preview
