from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import deps
from app.content.registry import ContentRegistry
from app.repositories.channels import ChannelRepository
from app.schemas.post import PostPreviewResponse

router = APIRouter(prefix="/preview", tags=["preview"])


@router.get("/{channel_id}", response_model=PostPreviewResponse)
async def preview_post(
    channel_id: uuid.UUID,
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    registry: ContentRegistry = Depends(deps.get_content_registry),
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
    return PostPreviewResponse(content=content, generated_at=now)
