from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class PostPreviewResponse(BaseModel):
    content: str
    generated_at: datetime
    image_url: str | None = None


class PostSendResponse(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    reason: str | None = None
    content: str | None = None
    image_url: str | None = None
    sent_at: datetime | None = None
