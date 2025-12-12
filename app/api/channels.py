import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.content.registry import ContentRegistry
from app.db.models import Channel
from app.repositories.channels import ChannelRepository
from app.repositories.posts import PostRepository
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate
from app.schemas.post import PostSendResponse
from app.services.image_generation import ImageGenerationService
from app.services.posting import PostingService
from app.telegram.client import TelegramClient

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("/", response_model=list[ChannelRead])
async def list_channels(channel_repo: ChannelRepository = Depends(deps.get_channel_repository)):
    return await channel_repo.list_channels()


@router.post("/", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
async def create_channel(
    payload: ChannelCreate,
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    session: AsyncSession = Depends(deps.get_session),
):
    channel = Channel(**payload.model_dump())
    created = await channel_repo.upsert_by_internal_name(channel)
    await session.commit()
    await session.refresh(created)
    return created


@router.put("/{channel_id}", response_model=ChannelRead)
async def update_channel(
    channel_id: uuid.UUID,
    payload: ChannelUpdate,
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    session: AsyncSession = Depends(deps.get_session),
):
    channel = await channel_repo.get(channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(channel, key, value)
    await session.commit()
    await session.refresh(channel)
    return channel


@router.post("/{channel_id}/auto-posting", response_model=ChannelRead)
async def set_auto_posting(
    channel_id: uuid.UUID,
    enabled: bool = Query(..., description="Enable or disable auto posting for the channel"),
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    session: AsyncSession = Depends(deps.get_session),
):
    channel = await channel_repo.get(channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    channel.auto_post_enabled = enabled
    await session.commit()
    await session.refresh(channel)
    return channel


@router.post("/{channel_id}/trigger-post", response_model=PostSendResponse)
async def trigger_post(
    channel_id: uuid.UUID,
    force: bool = Query(
        False,
        description="Отправить пост даже если не выполнены условия окна/частоты постинга",
    ),
    channel_repo: ChannelRepository = Depends(deps.get_channel_repository),
    post_repo: PostRepository = Depends(deps.get_post_repository),
    registry: ContentRegistry = Depends(deps.get_content_registry),
    telegram_client: TelegramClient = Depends(deps.get_telegram_client),
    image_generator: ImageGenerationService | None = Depends(deps.get_image_generator),
    session: AsyncSession = Depends(deps.get_session),
):
    channel = await channel_repo.get(channel_id)
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    posting_service = PostingService(registry, post_repo, telegram_client, image_generator)
    now = datetime.now(timezone.utc)

    if not force and not await posting_service.should_post(channel, now):
        return PostSendResponse(status="skipped", reason="Posting conditions not met (window/frequency)")

    try:
        content, image_url = await posting_service.create_and_send_post(channel, now)
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to send post") from exc

    await session.commit()

    if not content:
        return PostSendResponse(status="skipped", reason="No content generated")

    return PostSendResponse(status="sent", content=content, image_url=image_url, sent_at=now)
