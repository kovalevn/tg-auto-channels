import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.db.models.post import PostStatusEnum


class PostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_post(
        self,
        channel_id: uuid.UUID,
        content: str,
        status: str,
        scheduled_for: datetime,
        error: str | None = None,
        sent_at: datetime | None = None,
    ) -> Post:
        post = Post(
            channel_id=channel_id,
            content=content,
            status=status,
            scheduled_for=scheduled_for,
            error=error,
            sent_at=sent_at,
        )
        self.session.add(post)
        await self.session.flush()
        return post

    async def last_posts(self, channel_id: uuid.UUID, limit: int = 10) -> Sequence[Post]:
        result = await self.session.execute(
            select(Post).where(Post.channel_id == channel_id).order_by(desc(Post.created_at)).limit(limit)
        )
        return result.scalars().all()

    async def last_sent_post_time(self, channel_id: uuid.UUID) -> datetime | None:
        result = await self.session.execute(
            select(Post.sent_at)
            .where(Post.channel_id == channel_id, Post.status == PostStatusEnum.sent)
            .order_by(desc(Post.sent_at))
            .limit(1)
        )
        return result.scalar_one_or_none()
