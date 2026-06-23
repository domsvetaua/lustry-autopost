import anthropic
import base64
import os

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
    """Возвращает (fb_text, ig_text, fb_preview, ig_preview)"""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    char_block = ""
    if characteristics:
        char_block = f"""
Додаткові характеристики від продавця:
{characteristics}
Обов'язково використай ці характеристики в описі.
"""

    categories = "\n".join([f'- "{k}"' for k in BRAND_HASHTAGS.keys()])

    message = client.messages.create(
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
                    "text": f"""Ти — профессійний копірайтер магазину люстр "Дом Света" (Харків, Україна).

Подивись на фото і виконай завдання:

=== КРОК 1: КАТЕГОРІЯ ===
Визнач категорію з списку (вибери одну):
{categories}
{char_block}

=== КРОК 2: ПОСТ ДЛЯ FACEBOOK ===

Алгоритм Facebook 2026 — обов'язкові правила:
- Рядки 1-2: КРЮЧОК з емодзі — питання, факт або емоція (це єдине що видно до "читати далі")
- Рядки 3-8: опис товару з SEO-ключовими словами природно в тексті
- Рядки 9-10: переваги + конкретний CTA ("Напиши в повідомлення" або "Телефонуй")
- Передостанній рядок: питання для коментарів — просте і конкретне (генерує залученість)
- Рядок перед хештегами: "Більше [назва категорії] за хештегом [BRAND_HASHTAG]"
- Останній рядок: рівно 3 хештеги — #люстра + #харків + [BRAND_HASHTAG]
- НЕ додавай посилання на сайт в тексті (Facebook знижує охоплення)
- Довжина: 100-150 слів

=== КРОК 3: ПОСТ ДЛЯ INSTAGRAM ===

Алгоритм Instagram 2026 — обов'язкові правила:
- Рядки 1-2: КРЮЧОК з емодзі — інший ніж у Facebook, більш візуальний і емоційний
- Рядки 3-8: опис товару — більш образний і натхненний стиль ніж у Facebook
- Рядки 9-10: CTA з посиланням у шапці профілю
- Передостанній рядок: "Більше [назва категорії] у нас на сайті за посиланням у шапці профілю або за хештегом [BRAND_HASHTAG]"
- Останній рядок: рівно 5 хештегів — 1 широкий + 2 нішевих + 1 локальний #харків + [BRAND_HASHTAG]
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

    raw = message.content[0].text
    import logging; logging.getLogger(__name__).info(f"Claude raw response: {raw[:500]}")
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
        elif l in ("FACEBOOK:", "**FACEBOOK:**", "## FACEBOOK:", "### FACEBOOK:") or l.startswith("FACEBOOK:"):
            mode = "fb"
        elif l in ("INSTAGRAM:", "**INSTAGRAM:**", "## INSTAGRAM:", "### INSTAGRAM:") or l.startswith("INSTAGRAM:"):
            mode = "ig"
        elif l.startswith("ГЕОТЕГ:"):
            geotag = l.replace("ГЕОТЕГ:", "").strip()
            mode = None
        elif mode == "fb" and not l.startswith("INSTAGRAM") and not l.startswith("ГЕОТЕГ"):
            fb_text += line + "\n"
        elif mode == "ig" and not l.startswith("ГЕОТЕГ"):
            ig_text += line + "\n"

    fb_text = fb_text.strip()
    ig_text = ig_text.strip()

    # Подставляем брендовый хештег
    brand_hashtag = ""
    for key, (hashtag, category_name) in BRAND_HASHTAGS.items():
        if key in category:
            brand_hashtag = hashtag
            break

    if brand_hashtag:
        # Заменяем плейсхолдер
        fb_text = fb_text.replace("[BRAND_HASHTAG]", brand_hashtag)
        ig_text = ig_text.replace("[BRAND_HASHTAG]", brand_hashtag)

        # === FACEBOOK: оставляем только брендовый хештег ===
        fb_lines = fb_text.strip().split("\n")
        clean_fb_lines = []
        for line in fb_lines:
            stripped = line.strip()
            # Убираем строки с хештегами, кроме брендового
            if stripped.startswith("#") and brand_hashtag not in stripped:
                continue
            clean_fb_lines.append(line)
        fb_text = "\n".join(clean_fb_lines).strip()
        if brand_hashtag not in fb_text:
            fb_text += f"\n{brand_hashtag}"

        # === INSTAGRAM: брендовый хештег должен быть ВНУТРИ текста (после "за хештегом") ===
        # Убираем брендовый хештег если он стоит отдельной строкой в конце
        ig_lines = ig_text.strip().split("\n")
        # Проверяем последнюю строку — если там только брендовый хештег отдельно, убираем
        while ig_lines and ig_lines[-1].strip() == brand_hashtag:
            ig_lines.pop()
        ig_text = "\n".join(ig_lines).strip()

        # Проверяем что брендовый хештег есть в тексте (внутри фразы)
        if brand_hashtag not in ig_text:
            # Ищем фразу "за хештегом" и вставляем после неё
            if "за хештегом" in ig_text:
                ig_text = ig_text.replace("за хештегом", f"за хештегом {brand_hashtag}", 1)
            else:
                # Ищем последнюю строку с хештегами и добавляем туда
                ig_lines = ig_text.split("\n")
                for i in range(len(ig_lines)-1, -1, -1):
                    if ig_lines[i].strip().startswith("#"):
                        ig_lines[i] = ig_lines[i].rstrip() + f" {brand_hashtag}"
                        break
                else:
                    ig_text += f"\n{brand_hashtag}"
                ig_text = "\n".join(ig_lines)

    # Превью с геотегом для Instagram
    ig_preview = ig_text
    if geotag:
        ig_preview += f"\n\n📍 Геотег для ручного додавання: {geotag}"

    return fb_text, ig_text, fb_text, ig_preview
