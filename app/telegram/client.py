from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile
from aiogram import Bot

from app.core.config import get_settings


class TelegramClient:
    def __init__(self, token: str | None = None) -> None:
        settings = get_settings()
        self.bot = Bot(
            token=token or settings.telegram_bot_token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML,
            ),
        )

    async def send_message(self, channel_id: int, text: str) -> dict:
        message = await self.bot.send_message(chat_id=channel_id, text=text)
        return message.model_dump()

    async def send_photo(self, channel_id: int, photo: str | bytes, caption: str | None = None) -> dict:
        photo_payload = photo
        if isinstance(photo, bytes):
            photo_payload = BufferedInputFile(photo, filename="image.png")
        message = await self.bot.send_photo(chat_id=channel_id, photo=photo_payload, caption=caption)
        return message.model_dump()
