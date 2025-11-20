from datetime import datetime

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.db.models import Channel


class OpenAIChatGenerator:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate(self, channel: Channel, now: datetime) -> str:
        prompt = (
            "You are a Telegram content assistant. Generate a concise, engaging post for the channel. "
            f"Topic: {channel.topic}. Language code: {channel.language_code or 'en'}. "
            "Focus on value and include a call-to-action if relevant."
        )
        completion = await self.client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": prompt}],
            max_tokens=160,
            temperature=0.7,
        )
        return completion.choices[0].message.content or ""
