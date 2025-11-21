import uuid
from datetime import time

from pydantic import BaseModel, Field


class ChannelBase(BaseModel):
    internal_name: str
    telegram_channel_id: int
    topic: str
    language_code: str | None = None
    posting_frequency_per_day: int = Field(default=1, ge=1)
    posting_window_start: time | None = None
    posting_window_end: time | None = None
    timezone: str = "UTC"
    auto_post_enabled: bool = False
    content_strategy: str | None = None
    generate_images: bool = False


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    telegram_channel_id: int | None = None
    topic: str | None = None
    language_code: str | None = None
    posting_frequency_per_day: int | None = Field(default=None, ge=1)
    posting_window_start: time | None = None
    posting_window_end: time | None = None
    timezone: str | None = None
    auto_post_enabled: bool | None = None
    content_strategy: str | None = None
    generate_images: bool | None = None


class ChannelRead(ChannelBase):
    id: uuid.UUID

    class Config:
        from_attributes = True
