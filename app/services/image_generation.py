import logging

from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ImageGenerationService:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        if client is not None:
            self.client = client
        else:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for image generation")
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_image(self, prompt: str) -> str:
        response = await self.client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
            response_format="url",
        )
        if not response.data:
            raise RuntimeError("No image data returned from OpenAI")
        image_url = response.data[0].url
        if not image_url:
            raise RuntimeError("OpenAI returned an empty image URL")
        logger.info("Generated image for prompt length %s", len(prompt))
        return image_url
