from fastapi import Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.content.factory import build_content_registry
from app.content.registry import ContentRegistry
from app.db.session import get_session
from app.repositories.channels import ChannelRepository
from app.repositories.posts import PostRepository
from app.telegram.client import TelegramClient


def get_channel_repository(session: AsyncSession = Depends(get_session)) -> ChannelRepository:
    return ChannelRepository(session)


def get_post_repository(session: AsyncSession = Depends(get_session)) -> PostRepository:
    return PostRepository(session)


def get_content_registry() -> ContentRegistry:
    return build_content_registry()


def get_telegram_client() -> TelegramClient:
    return TelegramClient()
