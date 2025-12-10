import logging
import re
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.content.registry import ContentRegistry
from app.repositories.channels import ChannelRepository
from app.repositories.posts import PostRepository
from app.schemas.post import PostPreviewResponse
from app.services.image_generation import ImageGenerationService

router = APIRouter(prefix="/preview", tags=["preview"])
logger = logging.getLogger(__name__)


@router.get("/{channel_id}", response_model=PostPreviewResponse)
async def preview_post(
    channel_id: uuid.UUID,
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    registry: ContentRegistry = Depends(deps.get_content_registry),
    post_repo: PostRepository = Depends(deps.get_post_repository),
    image_generator: ImageGenerationService | None = Depends(deps.get_image_generator),
):
    channel = await channel_repo.get(channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    now = datetime.now(timezone.utc)
    strategy = channel.content_strategy or "placeholder"
    try:
        generator = registry.get(strategy)
    except KeyError:
        generator = registry.default()

    recent_posts = await post_repo.last_posts(channel.id, limit=50)
    recent_links = _extract_links_from_posts(recent_posts)

    content = await generator.generate(channel, now, recent_links=recent_links)
    image_url: str | None = None
    if channel.generate_images and image_generator:
        try:
            generated_image = await image_generator.generate_image(content)
            image_url = generated_image.url or generated_image.data_url
        except Exception:  # noqa: BLE001
            logger.exception("Failed to generate preview image for channel %s", channel.internal_name)

    return PostPreviewResponse(content=content, generated_at=now, image_url=image_url)


def _extract_links_from_posts(posts) -> set[str]:
    links: set[str] = set()
    url_regex = re.compile(r"https?://\S+")
    for post in posts:
        for match in url_regex.findall(post.content or ""):
            links.add(match.rstrip(").,"))
    return links
