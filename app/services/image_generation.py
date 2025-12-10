import base64
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class GeneratedImage:
    url: str | None
    image_bytes: bytes | None


class ImageGenerationService:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        if client is not None:
            self.client = client
        else:
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required for image generation")
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def generate_image(self, prompt: str) -> GeneratedImage:
        image_prompt = self._build_image_prompt(prompt)
        response = await self.client.images.generate(
            model="gpt-image-1",
            prompt=image_prompt,
            size="1024x1024",
        )
        if not response.data:
            raise RuntimeError("No image data returned from OpenAI")
        data = response.data[0]
        image_url = getattr(data, "url", None)
        b64_image = getattr(data, "b64_json", None)

        if not image_url and not b64_image:
            raise RuntimeError("No image data returned from OpenAI")

        image_bytes: bytes | None = None
        if b64_image:
            try:
                image_bytes = base64.b64decode(b64_image)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("Failed to decode base64 image from OpenAI") from exc

        logger.info("Generated image for prompt length %s", len(prompt))
        return GeneratedImage(url=image_url, image_bytes=image_bytes)

    @staticmethod
    def _build_image_prompt(post_content: str) -> str:
        return (
            "Create a high-quality image that illustrates the following post. "
            "Use subjects and scenes that best match the content. "
            "Do not include any text, captions, watermarks, or overlays. "
            f"Post content: {post_content}"
        )
