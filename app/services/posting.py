import logging
import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.content.registry import ContentRegistry
from app.db.models import Channel
from app.db.models.post import PostStatusEnum
from app.repositories.posts import PostRepository
from app.services.image_generation import ImageGenerationService
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
        image_generator: ImageGenerationService | None = None,
    ) -> None:
        self.content_registry = content_registry
        self.post_repo = post_repo
        self.telegram_client = telegram_client
        self.image_generator = image_generator

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

        recent_posts = await self.post_repo.last_posts(channel.id, limit=50)
        recent_links = self._extract_links_from_posts(recent_posts)

        content = await generator.generate(channel, now, recent_links=recent_links)
        if not content or not content.strip():
            logger.info("No content generated for channel %s, skipping send", channel.internal_name)
            return
        logger.info("Generated content for channel %s", channel.internal_name)
        scheduled_for = now
        image_url: str | None = None
        image_payload: str | bytes | None = None
        if channel.generate_images:
            if not self.image_generator:
                logger.warning("Image generation requested but no generator configured")
            else:
                try:
                    generated_image = await self.image_generator.generate_image(content)
                    image_url = generated_image.url or generated_image.data_url
                    if generated_image.url:
                        image_payload = generated_image.url
                    elif generated_image.image_bytes:
                        image_payload = generated_image.image_bytes
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to generate image for channel %s", channel.internal_name)
                    image_url = None

        try:
            if image_payload:
                await self.telegram_client.send_photo(
                    channel.telegram_channel_id,
                    photo=image_payload,
                    caption=content,
                )
            else:
                await self.telegram_client.send_message(channel.telegram_channel_id, content)
            await self.post_repo.record_post(
                channel_id=channel.id,
                content=content,
                image_url=image_url,
                status=PostStatusEnum.sent,
                scheduled_for=scheduled_for,
                sent_at=now,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send post to channel %s", channel.internal_name)
            await self.post_repo.record_post(
                channel_id=channel.id,
                content=content,
                image_url=image_url,
                status=PostStatusEnum.failed,
                scheduled_for=scheduled_for,
                error=str(exc),
            )
            raise

    @staticmethod
    def _extract_links_from_posts(posts) -> set[str]:
        links: set[str] = set()
        url_regex = re.compile(r"https?://\S+")
        for post in posts:
            for match in url_regex.findall(post.content or ""):
                links.add(match.rstrip(").,"))
        return links
