from datetime import datetime
from typing import Protocol

from app.db.models import Channel


class ContentGenerator(Protocol):
    async def generate(self, channel: Channel, now: datetime, recent_links: set[str] | None = None) -> str: ...
