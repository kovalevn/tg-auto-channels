import asyncio
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Iterable
from urllib.parse import urlparse

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
        selection_pool_size: int = 5,
        request_timeout: int = 10,
    ) -> None:
        settings = get_settings()
        self.client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self.lookback_hours = lookback_hours
        self.max_entries_per_source = max_entries_per_source
        self.selection_pool_size = max(1, selection_pool_size)
        self.request_timeout = request_timeout

    async def generate(self, channel: Channel, now: datetime, recent_links: set[str] | None = None) -> str:
        sources = self._flatten_sources(channel.news_source_lists)
        if not sources:
            return (
                "Для канала нет активных новостных источников. "
                "Добавьте RSS/Atom ленты, чтобы получать материалы."
            )

        now_utc = now.astimezone(timezone.utc)
        cutoff = now_utc - timedelta(hours=self.lookback_hours)
        candidates = await self._collect_candidates(sources, cutoff, now_utc)
        if not candidates:
            return "Свежих публикаций за выбранный период не найдено."

        seen_links = {self._normalize_link(link) for link in (recent_links or set()) if link}
        filtered = [c for c in candidates if self._normalize_link(c.link) not in seen_links]
        if filtered:
            candidates = filtered
        elif seen_links:
            return "Свежих новостей без повторов не нашлось."

        best_candidate = self._pick_best_candidate(candidates, now_utc)
        return await self._summarize_candidate(best_candidate, channel.language_code or "ru")

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

    def _pick_best_candidate(self, candidates: list[NewsCandidate], now_utc: datetime) -> NewsCandidate:
        """Pick from a pool of the freshest items, favoring article-like entries."""
        sorted_candidates = sorted(candidates, key=lambda item: item.published_at, reverse=True)
        pool = sorted_candidates[: self.selection_pool_size]

        preferred = [c for c in pool if self._is_probably_article(c)]
        if preferred:
            pool = preferred

        rng = random.Random(int(now_utc.timestamp()))
        return rng.choice(pool)

    def _is_probably_article(self, candidate: NewsCandidate) -> bool:
        summary_text = self._squash_spaces(candidate.summary)
        if len(summary_text) < 20:
            return False
        if self._looks_like_section_link(candidate.link):
            return False
        return True

    @staticmethod
    def _squash_spaces(text: str) -> str:
        return " ".join(text.split())

    def _looks_like_section_link(self, link: str) -> bool:
        parsed = urlparse(link)
        path = parsed.path.lower()
        section_markers = (
            "section",
            "sections",
            "category",
            "categories",
            "specials",
            "topics",
            "tags",
            "collections",
        )
        if any(f"/{marker}" in path for marker in section_markers):
            return True
        if parsed.query and "section" in parsed.query.lower():
            return True
        return False

    @staticmethod
    def _normalize_link(link: str) -> str:
        try:
            parsed = urlparse(link)
        except Exception:
            return link
        if not parsed.netloc:
            return link
        scheme = parsed.scheme.lower() or "http"
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        return f"{scheme}://{netloc}{path}"

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
                    title=str(entry.get("title", "Без заголовка")),
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

    async def _summarize_candidate(self, candidate: NewsCandidate, language_code: str = "ru") -> str:
        article_text = await self._fetch_article_text(candidate.link)
        article_text = self._squash_spaces(article_text)
        summary_text = self._squash_spaces(candidate.summary)

        combined_context = f"{summary_text}\n\n{article_text}".strip() or summary_text or article_text or candidate.title
        combined_context = combined_context[:4000]  # keep prompt compact

        prompt = (
            "Ты редактор новостного телеграм-канала. Тебе дают заголовок, выдержку из RSS и (если удалось) "
            "текст статьи. Сформулируй 1–2 предложения о главном событии статьи на указанном языке. "
            "Не описывай разделы или рубрики, не добавляй выдуманных подробностей — опирайся только на текст. "
            "Заверши строкой 'Источник: <url>'."
        )

        user_message = (
            f"Язык: {language_code}\n"
            f"Заголовок: {candidate.title}\n"
            f"Краткое описание из RSS: {summary_text}\n"
            f"Текст статьи (если есть): {combined_context}\n"
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

    async def _fetch_article_text(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.request_timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.info("Failed to fetch article text from %s: %s", url, exc)
            return ""

        return self._extract_text_from_html(response.text)

    @staticmethod
    def _extract_text_from_html(html: str) -> str:
        """Very lightweight HTML-to-text conversion without extra deps."""
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = unescape(text)
        text = " ".join(text.split())
        return text.strip()
