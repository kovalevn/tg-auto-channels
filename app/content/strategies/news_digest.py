import asyncio
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Iterable
from urllib.parse import urlparse, quote_plus

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
    """Generates short news posts from configured RSS/Atom feeds."""

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
            return ""

        now_utc = now.astimezone(timezone.utc)
        cutoff = now_utc - timedelta(hours=self.lookback_hours)
        candidates = await self._collect_candidates(sources, cutoff, now_utc)
        if not candidates:
            logger.info("No news candidates for channel %s within last %sh", channel.id, self.lookback_hours)
            return ""

        seen_links = {self._normalize_link(link) for link in (recent_links or set()) if link}
        filtered = [c for c in candidates if self._normalize_link(c.link) not in seen_links]
        if filtered:
            logger.debug(
                "Candidate filtering: total=%d, unique=%d, seen_links=%d for channel %s",
                len(candidates),
                len(filtered),
                len(seen_links),
                channel.id,
            )
            candidates = filtered
        elif seen_links:
            logger.info(
                "All %d candidates already seen for channel %s; skipping generation",
                len(candidates),
                channel.id,
            )
            return ""
        else:
            logger.debug(
                "Candidate filtering: total=%d, no seen_links for channel %s",
                len(candidates),
                channel.id,
            )

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
        summary_text = self._squash_spaces(candidate.summary)
        article_text = await self._fetch_article_text(candidate.link)
        article_text = self._squash_spaces(article_text)
        combined_context = f"{summary_text}\n\n{article_text}".strip() or summary_text or article_text or ""
        combined_context = combined_context[:1500]

        prompt = (
            "Ты пишешь короткую новостную заметку по одной новости из RSS. Всегда используй язык канала; не вставляй "
            "английские слова, если язык канала другой. Не придумывай факты и оценки, только из предоставленного текста. "
            "Уложись в 800–900 знаков.\n"
            "Строго следуй шаблону (верни только текст поста в этом формате):\n"
            "⚡️ **<краткий заголовок>\n"
            "\n"
            "<абзац 1 с фактами>\n"
            "\n"
            "<абзац 2 с деталями> (допускается абзац 3, если нужно)\n"
            "\n"
            "**ПОЧЕМУ ЭТО ВАЖНО:** <пояснение значимости>\n"
            "\n"
            "[Источник](<url>)\n"
            "Требования: абзацы разделяй пустой строкой, заголовок и блок 'ПОЧЕМУ ЭТО ВАЖНО' обязаны быть, ссылка на "
            "источник в конце. Если данных мало, пиши кратко, но соблюдай шаблон."
        )

        user_message = (
            f"Язык канала: {language_code}\n"
            f"Заголовок из RSS: {candidate.title}\n"
            f"Краткое описание из RSS: {summary_text}\n"
            f"Контекст статьи или заметки: {combined_context}\n"
            f"Ссылка на материал: {candidate.link}\n"
            f"Название источника: {candidate.source}"
        )

        completion = await self.client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message},
            ],
            max_completion_tokens=320,
            temperature=0.2,
        )

        choice = completion.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        digest = self._extract_choice_text(choice)

        if digest:
            return digest

        logger.warning(
            "Empty digest from model for %s (finish_reason=%s, prompt_tokens=%s, completion_tokens=%s, refusal=%s)",
            candidate.link,
            finish_reason,
            getattr(completion.usage, "prompt_tokens", None),
            getattr(completion.usage, "completion_tokens", None),
            getattr(getattr(choice, "message", None), "refusal", None),
        )

        retry_text = await self._retry_summarize(candidate, language_code, summary_text)
        return retry_text

    async def _retry_summarize(self, candidate: NewsCandidate, language_code: str, summary_text: str) -> str:
        """Second attempt with reduced context to avoid content filters."""
        trimmed_summary = (summary_text or "").strip()[:1000]
        retry_user_message = (
            f"Язык канала: {language_code}\n"
            f"Заголовок из RSS: {candidate.title}\n"
            f"Краткое описание из RSS: {trimmed_summary}\n"
            f"Контекст статьи или заметки: {trimmed_summary}\n"
            f"Ссылка на материал: {candidate.link}\n"
            f"Название источника: {candidate.source}"
        )

        completion = await self.client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {"role": "system", "content": "Сформируй новостную заметку по тому же формату, даже если контекст усечён."},
                {"role": "user", "content": retry_user_message},
            ],
            max_completion_tokens=260,
            temperature=0.2,
        )

        choice = completion.choices[0]
        finish_reason = getattr(choice, "finish_reason", None)
        text = self._extract_choice_text(choice)

        if not text:
            logger.error(
                "Retry digest is still empty for %s (finish_reason=%s, prompt_tokens=%s, completion_tokens=%s, refusal=%s)",
                candidate.link,
                finish_reason,
                getattr(completion.usage, "prompt_tokens", None),
                getattr(completion.usage, "completion_tokens", None),
                getattr(getattr(choice, "message", None), "refusal", None),
            )
        return text

    @staticmethod
    def _extract_choice_text(choice: Any) -> str:
        """Handle both string and structured content responses from OpenAI."""
        message = getattr(choice, "message", None)
        if not message:
            return ""

        content = getattr(message, "content", None)

        if isinstance(content, str):
            return content.strip()

        # Newer API versions can return content as a list of parts
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                text_value: str | None = None
                if isinstance(part, dict):
                    text_value = part.get("text") or part.get("output_text")
                else:
                    text_value = getattr(part, "text", None) or getattr(part, "output_text", None)
                if text_value:
                    parts.append(str(text_value))
                else:
                    parts.append(str(part))
            extracted = "\n".join(parts).strip()
            if not extracted:
                logger.debug("Empty content parts extracted; raw parts=%s", content)
            return extracted

        logger.debug("Unhandled message content type %s: %r", type(content), content)
        return ""

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
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        paragraphs = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
        cleaned: list[str] = []
        for raw in paragraphs:
            text = re.sub(r"(?is)<[^>]+>", " ", raw)
            text = unescape(text)
            text = " ".join(text.split()).strip()
            if len(text) < 20:
                continue
            if NewsDigestGenerator._looks_like_boilerplate(text):
                continue
            cleaned.append(text)
        if cleaned:
            return "\n".join(cleaned)
        text = re.sub(r"(?is)<[^>]+>", " ", html)
        text = unescape(text)
        text = " ".join(text.split())
        return text.strip()

    @staticmethod
    def _looks_like_boilerplate(text: str) -> bool:
        lowered = text.lower()
        boilerplate_keywords = (
            "cookies",
            "privacy",
            "navigation",
            "menu",
            "subscribe",
            "newsletter",
            "sign up",
            "manage subscription",
            "settings",
            "notification",
            "page not found",
            "content not available",
            "does not exist",
            "unavailable",
            "video player",
            "enable tracking",
            "adblock",
            "browser extension",
            "sign up for newsletters",
            "register to watch",
            "play video",
            "skip to main",
            "main content",
            "offline navigation",
            "menu menu",
        )
        return any(k in lowered for k in boilerplate_keywords)

    @staticmethod
    def _google_translate_link(link: str, target_lang: str) -> str:
        if not link:
            return ""
        encoded = quote_plus(link)
        return f"https://translate.google.com/translate?hl={target_lang}&sl=auto&tl={target_lang}&u={encoded}"
