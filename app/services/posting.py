import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.content.registry import ContentRegistry
from app.db.models import Channel
from app.db.models.post import PostStatusEnum
from app.repositories.posts import PostRepository
from app.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


def _in_window(now_local: datetime, start: time | None, end: time | None) -> bool:
    if start is None or end is None:
        return True
    start_dt = now_local.replace(hour=start.hour, minute=start.minute, second=start.second, microsecond=0)
    end_dt = now_local.replace(hour=end.hour, minute=end.minute, second=end.second, microsecond=0)
    if start_dt <= end_dt:
        return start_dt <= now_local <= end_dt
    # window across midnight
    return now_local >= start_dt or now_local <= end_dt


class PostingService:
    def __init__(
        self,
        content_registry: ContentRegistry,
        post_repo: PostRepository,
        telegram_client: TelegramClient,
    ) -> None:
        self.content_registry = content_registry
        self.post_repo = post_repo
        self.telegram_client = telegram_client

    async def should_post(self, channel: Channel, now: datetime) -> bool:
        tz = ZoneInfo(channel.timezone)
        now_local = now.astimezone(tz)
        if not _in_window(now_local, channel.posting_window_start, channel.posting_window_end):
            return False

        min_interval = timedelta(hours=24 / max(channel.posting_frequency_per_day, 1))
        last_sent = await self.post_repo.last_sent_post_time(channel.id)
        if last_sent is None:
            return True
        return now - last_sent >= min_interval

    async def create_and_send_post(self, channel: Channel, now: datetime) -> None:
        strategy_name = channel.content_strategy or "placeholder"
        try:
            generator = self.content_registry.get(strategy_name)
        except KeyError:
            logger.warning("Strategy %s not registered, using default", strategy_name)
            generator = self.content_registry.default()

        content = await generator.generate(channel, now)
        logger.info("Generated content for channel %s", channel.internal_name)
        scheduled_for = now

        try:
            await self.telegram_client.send_message(channel.telegram_channel_id, content)
            await self.post_repo.record_post(
                channel_id=channel.id,
                content=content,
                status=PostStatusEnum.sent,
                scheduled_for=scheduled_for,
                sent_at=now,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send post to channel %s", channel.internal_name)
            await self.post_repo.record_post(
                channel_id=channel.id,
                content=content,
                status=PostStatusEnum.failed,
                scheduled_for=scheduled_for,
                error=str(exc),
            )
            raise
