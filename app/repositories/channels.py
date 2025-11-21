import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Channel


class ChannelRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_channels(self) -> Sequence[Channel]:
        result = await self.session.execute(select(Channel))
        return result.scalars().all()

    async def get(self, channel_id: uuid.UUID) -> Channel | None:
        result = await self.session.execute(select(Channel).where(Channel.id == channel_id))
        return result.scalar_one_or_none()

    async def get_by_internal_name(self, name: str) -> Channel | None:
        result = await self.session.execute(select(Channel).where(Channel.internal_name == name))
        return result.scalar_one_or_none()

    async def create(self, channel: Channel) -> Channel:
        self.session.add(channel)
        await self.session.flush()
        return channel

    async def upsert_by_internal_name(self, channel: Channel) -> Channel:
        existing = await self.get_by_internal_name(channel.internal_name)
        if existing:
            for attr in (
                "telegram_channel_id",
                "topic",
                "language_code",
                "posting_frequency_per_day",
                "posting_window_start",
                "posting_window_end",
                "timezone",
                "auto_post_enabled",
                "content_strategy",
                "generate_images",
            ):
                setattr(existing, attr, getattr(channel, attr))
            await self.session.flush()
            return existing
        return await self.create(channel)
