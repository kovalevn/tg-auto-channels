import logging
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.content.registry import ContentRegistry
from app.repositories.channels import ChannelRepository
from app.schemas.post import PostPreviewResponse
from app.services.image_generation import ImageGenerationService

router = APIRouter(prefix="/preview", tags=["preview"])
logger = logging.getLogger(__name__)


@router.get("/{channel_id}", response_model=PostPreviewResponse)
async def preview_post(
    channel_id: uuid.UUID,
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    registry: ContentRegistry = Depends(deps.get_content_registry),
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
    content = await generator.generate(channel, now)
    image_url: str | None = None
    if channel.generate_images and image_generator:
        try:
            image_url = await image_generator.generate_image(content)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to generate preview image for channel %s", channel.internal_name)

    return PostPreviewResponse(content=content, generated_at=now, image_url=image_url)
