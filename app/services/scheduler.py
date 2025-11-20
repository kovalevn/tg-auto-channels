import logging
from datetime import datetime, timezone

from collections.abc import Callable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.channels import ChannelRepository
from app.repositories.posts import PostRepository
from app.services.posting import PostingService

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        posting_service_builder: Callable[[PostRepository], PostingService],
    ) -> None:
        self.session_factory = session_factory
        self.posting_service_builder = posting_service_builder

    async def run_tick(self) -> None:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session:
            channel_repo = ChannelRepository(session)
            post_repo = PostRepository(session)
            posting_service: PostingService = self.posting_service_builder(post_repo)
            channels = await channel_repo.list_channels()
            for channel in channels:
                if not channel.auto_post_enabled:
                    continue
                if await posting_service.should_post(channel, now):
                    await posting_service.create_and_send_post(channel, now)
            await session.commit()


class SchedulerRunner:
    def __init__(self, service: SchedulerService, interval_minutes: int) -> None:
        self.service = service
        self.interval_minutes = interval_minutes
        self.scheduler = AsyncIOScheduler()

    def start(self) -> None:
        self.scheduler.add_job(self.service.run_tick, "interval", minutes=self.interval_minutes, id="posting-tick")
        logger.info("Starting scheduler with %s minute interval", self.interval_minutes)
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown()
