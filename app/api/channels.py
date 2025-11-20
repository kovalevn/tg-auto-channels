import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models import Channel
from app.repositories.channels import ChannelRepository
from app.schemas.channel import ChannelCreate, ChannelRead, ChannelUpdate

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
