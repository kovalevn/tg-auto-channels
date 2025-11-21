from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import channels, health, preview
from app.content.factory import build_content_registry
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.services.image_generation import ImageGenerationService
from app.services.posting import PostingService
from app.services.scheduler import SchedulerRunner, SchedulerService
from app.telegram.client import TelegramClient

settings = get_settings()
content_registry = build_content_registry()
telegram_client = TelegramClient()
try:
    image_generator = ImageGenerationService()
except ValueError:
    image_generator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    with configure_logging():
        scheduler_service = SchedulerService(
            session_factory=SessionLocal,
            posting_service_builder=lambda post_repo: PostingService(
                content_registry, post_repo, telegram_client, image_generator
            ),
        )
        runner = SchedulerRunner(scheduler_service, interval_minutes=settings.posting_interval_minutes)
        runner.start()
        try:
            yield
        finally:
            runner.shutdown()
            await telegram_client.bot.session.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(channels.router)
    app.include_router(preview.router)
    return app


app = create_app()
