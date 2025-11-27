from app.content.registry import ContentRegistry
from app.content.strategies.news_digest import NewsDigestGenerator
from app.content.strategies.openai_chat import OpenAIChatGenerator
from app.content.strategies.placeholder import PlaceholderGenerator
from app.core.config import get_settings


def build_content_registry() -> ContentRegistry:
    settings = get_settings()
    registry = ContentRegistry()
    registry.register("placeholder", PlaceholderGenerator())
    if settings.openai_api_key:
        registry.register("openai", OpenAIChatGenerator())
        registry.register("news", NewsDigestGenerator())
    return registry
