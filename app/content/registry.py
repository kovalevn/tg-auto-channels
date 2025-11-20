from typing import Dict

from app.content.interfaces import ContentGenerator


class ContentRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, ContentGenerator] = {}

    def register(self, name: str, generator: ContentGenerator) -> None:
        self._registry[name] = generator

    def get(self, name: str) -> ContentGenerator:
        if name not in self._registry:
            raise KeyError(f"Content generator '{name}' not registered")
        return self._registry[name]

    def default(self) -> ContentGenerator:
        if not self._registry:
            raise RuntimeError("No content generators registered")
        return self._registry[next(iter(self._registry))]
