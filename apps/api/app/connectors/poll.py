"""Poll one feed source: conditional GET, parse, ingest new entries (FR-90, FR-07).

Runs as a ``poll`` job (``handle_poll``). Failures are recorded on the source row
(``error_count``, ``last_polled_at``) and logged without bodies; the job still completes so a
broken feed never blocks the queue. Idempotency comes from ``ingest_one`` on (source, source_ref).
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.feed_parse import FeedEntry, FeedParseError, parse_feed
from app.connectors.feed_urls import TYPE_HN, FeedConfigError, feed_url
from app.connectors.hn import parse_hn
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.ingest.service import ingest_one
from app.integrations.ssrf import UnsafeUrl, check_url
from app.models.job import Job
from app.models.source import Source
from app.schemas.ingest import Hints, IngestItemIn

log = get_logger("app.connectors.poll")

POLL_INTERVAL = timedelta(minutes=15)  # docs/CONNECTORS.md: feeds poll every 15 min
FEED_SOURCE = "rss"  # item source for every feed type (SOURCE_DEFAULTS: public)
FEED_TIMEOUT_S = 15.0
MAX_FEED_BYTES = 2_000_000
DEFAULT_NICHE = "news_radar"
POLL_SOURCE_KEY = "source_id"
NOT_MODIFIED = 304
RECOVERABLE = (FeedConfigError, FeedParseError, UnsafeUrl, httpx.HTTPError, TimeoutError)


@dataclass(frozen=True)
class FetchResult:
    status_code: int
    body: bytes
    etag: str | None
    last_modified: str | None


@dataclass(frozen=True)
class PollResult:
    new_items: int
    not_modified: bool


def conditional_headers(cursor: dict[str, Any] | None) -> dict[str, str]:
    """If-None-Match / If-Modified-Since from the stored cursor (HTTP caching, FR-90)."""
    headers: dict[str, str] = {}
    if not cursor:
        return headers
    etag, last_modified = cursor.get("etag"), cursor.get("last_modified")
    if isinstance(etag, str) and etag:
        headers["If-None-Match"] = etag
    if isinstance(last_modified, str) and last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


async def _read_capped(response: httpx.Response) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_FEED_BYTES:
            raise FeedParseError("feed body exceeds the size cap")
        chunks.append(chunk)
    return b"".join(chunks)


async def fetch_feed(
    url: str,
    cursor: dict[str, Any] | None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """GET ``url`` through the SSRF guard. Raises UnsafeUrl or an httpx error on failure."""
    check_url(url, allow_private=get_settings().webhook_allow_private_urls)
    async with (
        asyncio.timeout(FEED_TIMEOUT_S),
        httpx.AsyncClient(
            timeout=FEED_TIMEOUT_S,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        ) as client,
        client.stream("GET", url, headers=conditional_headers(cursor)) as response,
    ):
        if response.status_code == NOT_MODIFIED:
            return FetchResult(NOT_MODIFIED, b"", None, None)
        response.raise_for_status()
        body = await _read_capped(response)
        return FetchResult(
            response.status_code,
            body,
            response.headers.get("etag"),
            response.headers.get("last-modified"),
        )


def parse_entries(feed_type: str, body: bytes) -> list[FeedEntry]:
    return parse_hn(body) if feed_type == TYPE_HN else parse_feed(body)


def _safe_url(link: str | None) -> str | None:
    """Keep only links Hints accepts (absolute http(s) with a host); others are dropped."""
    if not link:
        return None
    parts = urlsplit(link)
    return link if parts.scheme in ("http", "https") and parts.netloc else None


def entry_to_ingest(source: Source, entry: FeedEntry) -> IngestItemIn:
    """Map one feed entry to an ingest payload. The payload keeps the raw fields (FR-06)."""
    hints = Hints(
        niche=source.niche_hint or DEFAULT_NICHE,
        title=entry.title,
        body=entry.summary or None,
        url=_safe_url(entry.link),
    )
    payload = {
        "feed": source.slug,
        "title": entry.title,
        "link": entry.link,
        "summary": entry.summary,
        "published": entry.published.isoformat() if entry.published else None,
    }
    return IngestItemIn(source=FEED_SOURCE, source_ref=entry.ref, payload=payload, hints=hints)


async def _ingest_entries(session: AsyncSession, source: Source, entries: list[FeedEntry]) -> int:
    created = 0
    for entry in entries:
        _, is_new = await ingest_one(session, source.tenant_id, entry_to_ingest(source, entry))
        created += int(is_new)
    return created


async def poll_source(
    session: AsyncSession,
    source: Source,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PollResult:
    """Fetch, parse and ingest one source. Raises RECOVERABLE errors; the caller records them."""
    url = feed_url(source.type, source.config or {})
    fetched = await fetch_feed(url, source.cursor, transport=transport)
    if fetched.status_code == NOT_MODIFIED:
        return PollResult(new_items=0, not_modified=True)
    entries = parse_entries(source.type, fetched.body)
    created = await _ingest_entries(session, source, entries)
    source.cursor = {"etag": fetched.etag, "last_modified": fetched.last_modified}
    return PollResult(new_items=created, not_modified=False)


def record_success(source: Source, result: PollResult) -> None:
    source.error_count = 0
    source.last_polled_at = utcnow()
    log.info(
        "feed polled",
        extra={
            "feed": source.slug,
            "new_items": result.new_items,
            "not_modified": result.not_modified,
        },
    )


def record_failure(source: Source, error: Exception) -> None:
    source.error_count = source.error_count + 1
    source.last_polled_at = utcnow()
    log.warning("feed poll failed", extra={"feed": source.slug, "error": type(error).__name__})


async def _load_source(session: AsyncSession, job: Job) -> Source | None:
    source_id = (job.payload or {}).get(POLL_SOURCE_KEY)
    if not isinstance(source_id, str):
        return None
    stmt = select(Source).where(Source.id == source_id, Source.tenant_id == job.tenant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def handle_poll(session: AsyncSession, job: Job) -> None:
    """POLL job handler. The worker commits after this returns."""
    source = await _load_source(session, job)
    if source is None or not source.enabled:
        return
    try:
        result = await poll_source(session, source)
    except RECOVERABLE as error:
        record_failure(source, error)
        return
    record_success(source, result)
