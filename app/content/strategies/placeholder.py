from datetime import datetime

from app.db.models import Channel


class PlaceholderGenerator:
    async def generate(self, channel: Channel, now: datetime, recent_links: set[str] | None = None) -> str:
        return (
            f"[{now.isoformat()}] Updates for {channel.internal_name} (topic: {channel.topic}). "
            f"Stay tuned!"
        )
