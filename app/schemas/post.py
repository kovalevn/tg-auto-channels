from datetime import datetime

from pydantic import BaseModel


class PostPreviewResponse(BaseModel):
    content: str
    generated_at: datetime
    image_url: str | None = None
