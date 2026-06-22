import anthropic
import base64
import os

async def generate_post_text(photo_bytes: bytes) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    image_data = base64.standard_b64encode(photo_bytes).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": """Ты — профессиональный копирайтер для интернет-магазина люстр и светильников.

Посмотри на фото люстры и создай продающий пост для Facebook и Instagram.

Требования к посту:
1. Начни с яркого цепляющего заголовка с эмодзи
2. Опиши люстру: стиль, материал, дизайн, для каких интерьеров подходит
3. Укажи преимущества и выгоды для покупателя
4. Добавь призыв к действию (написать в директ или позвонить)
5. В конце добавь 15-20 релевантных хештегов на русском и английском

Пиши на русском языке. Текст должен быть эмоциональным и продающим."""
                    }
                ],
            }
        ],
    )

    return message.content[0].text
