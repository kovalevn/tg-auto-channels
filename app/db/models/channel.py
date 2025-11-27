import uuid
from datetime import time

from sqlalchemy import Boolean, Integer, JSON, String, Text, Time, Uuid, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    internal_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    telegram_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    posting_frequency_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    posting_window_start: Mapped[time | None] = mapped_column(Time(), nullable=True)
    posting_window_end: Mapped[time | None] = mapped_column(Time(), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    auto_post_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    generate_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    news_source_lists: Mapped[list[list[str]] | None] = mapped_column(JSON, nullable=True)

    posts: Mapped[list["Post"]] = relationship("Post", back_populates="channel", cascade="all, delete-orphan")
