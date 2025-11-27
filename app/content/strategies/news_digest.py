import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import feedparser
import httpx
from openai import AsyncOpenAI

from app.core.config import get_settings
from app.db.models import Channel

logger = logging.getLogger(__name__)


@dataclass
class NewsCandidate:
    title: str
    link: str
    summary: str
    published_at: datetime
    source: str


class NewsDigestGenerator:
    """Generates a short Russian news digest from configured feeds."""

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        lookback_hours: int = 24,
        max_entries_per_source: int = 5,
        request_timeout: int = 10,
    ) -> None:
        settings = get_settings()
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self.lookback_hours = lookback_hours
        self.max_entries_per_source = max_entries_per_source
        self.request_timeout = request_timeout

    async def generate(self, channel: Channel, now: datetime) -> str:
        sources = self._flatten_sources(channel.news_source_lists)
        if not sources:
            return (
                "Не настроены источники новостей для этого канала. "
                "Добавьте RSS/Atom ссылки, чтобы получать дайджесты."
            )

        now_utc = now.astimezone(timezone.utc)
        cutoff = now_utc - timedelta(hours=self.lookback_hours)
        candidates = await self._collect_candidates(sources, cutoff, now_utc)
        if not candidates:
            return "Свежих новостей из подключенных источников не нашлось."

        best_candidate = sorted(candidates, key=lambda item: item.published_at, reverse=True)[0]
        return await self._summarize_candidate(best_candidate)

    @staticmethod
    def _flatten_sources(source_lists: list[list[str]] | None) -> list[str]:
        if not source_lists:
            return []
        return [url for group in source_lists for url in group if url]

    async def _collect_candidates(
        self, sources: list[str], cutoff: datetime, now_utc: datetime
    ) -> list[NewsCandidate]:
        async with httpx.AsyncClient(timeout=self.request_timeout) as client:
            fetch_tasks = [self._fetch_feed(client, url, cutoff, now_utc) for url in sources]
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        candidates: list[NewsCandidate] = []
        for source_url, result in zip(sources, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("Failed to fetch feed %s: %s", source_url, result)
                continue
            candidates.extend(result)
        return candidates

    async def _fetch_feed(
        self,
        client: httpx.AsyncClient,
        url: str,
        cutoff: datetime,
        now_utc: datetime,
    ) -> list[NewsCandidate]:
        response = await client.get(url)
        parsed = feedparser.parse(response.text)

        feed_title = parsed.feed.get("title", url) if parsed.feed else url
        entries: list[NewsCandidate] = []

        for entry in parsed.entries[: self.max_entries_per_source]:
            published_at = self._extract_datetime(entry, now_utc)
            if published_at < cutoff:
                continue
            entries.append(
                NewsCandidate(
                    title=str(entry.get("title", "Без названия")),
                    link=str(entry.get("link", url)),
                    summary=str(self._extract_summary(entry)),
                    published_at=published_at,
                    source=feed_title,
                )
            )

        return entries

    @staticmethod
    def _extract_summary(entry: Any) -> str:
        for key in ("summary", "description", "content"):
            value = entry.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, Iterable):
                try:
                    first_item = next(iter(value))
                    if isinstance(first_item, dict) and "value" in first_item:
                        return str(first_item["value"])
                except StopIteration:
                    continue
        return ""

    @staticmethod
    def _extract_datetime(entry: Any, fallback: datetime) -> datetime:
        for key in ("published_parsed", "updated_parsed", "created_parsed"):
            value = entry.get(key)
            if value:
                try:
                    return datetime(*value[:6], tzinfo=timezone.utc)
                except Exception:  # noqa: BLE001
                    continue
        return fallback

    async def _summarize_candidate(self, candidate: NewsCandidate) -> str:
        prompt = (
            "Ты новостной редактор. Найди ключевые факты, кратко изложи их на русском языке, "
            "а если исходный текст не на русском — переведи. Сделай 2-3 коротких предложения "
            "без лишних деталей. Заверши блоком 'Источник: <url>'."
        )

        user_message = (
            f"Заголовок: {candidate.title}\n"
            f"Краткое описание: {candidate.summary}\n"
            f"Ссылка: {candidate.link}\n"
            f"Источник: {candidate.source}"
        )

        completion = await self.client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=180,
            temperature=0.3,
        )

        digest = completion.choices[0].message.content or ""
        digest = digest.strip()
        if "Источник:" not in digest:
            digest = f"{digest}\n\nИсточник: {candidate.link}"
        return digest
