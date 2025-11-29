from datetime import datetime

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.db.models import Channel


class OpenAIChatGenerator:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate(self, channel: Channel, now: datetime, recent_links: set[str] | None = None) -> str:
        user_prompt = f"{channel.topic}\nLanguage code: {channel.language_code or 'en'}"

        completion = await self.client.chat.completions.create(
            model="gpt-5.1",
            messages=[{"role": "user", "content": user_prompt}],
            max_completion_tokens=200,
            temperature=0.7,
        )
        return completion.choices[0].message.content or ""
