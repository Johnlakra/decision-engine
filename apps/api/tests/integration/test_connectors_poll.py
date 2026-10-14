"""Feed polling end to end: ingest, conditional GET, failures and scheduling (FR-90, FR-07)."""

import uuid
from collections.abc import Callable, Coroutine
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors import poll as poll_module
from app.connectors.feed_parse import FeedEntry
from app.connectors.poll import FEED_SOURCE, entry_to_ingest, handle_poll, poll_source
from app.connectors.schedule import enqueue_due_polls
from app.core.time import utcnow
from app.models import Item, Job, Source, Tenant
from app.models.enums import JobKind
from app.workers import queue

pytestmark = pytest.mark.integration

FEED_URL = "https://feeds.example.com/news.xml"
ETAG = '"v1"'
RSS = b"""<rss><channel>
  <item><title>Beta opens</title><link>https://example.com/beta</link><guid>g-1</guid></item>
  <item><title>Credits</title><link>https://example.com/credits</link><guid>g-2</guid></item>
</channel></rss>"""

Fetch = Callable[..., Coroutine[Any, Any, poll_module.FetchResult]]


def mock_transport(status: int, body: bytes = RSS) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body, headers={"ETag": ETAG})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def skip_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SSRF guard resolves hosts; these tests exercise the poller, not DNS."""
    monkeypatch.setattr(poll_module, "check_url", lambda url, **_: [])


async def make_source(session: AsyncSession, tenant: Tenant, slug: str = "demo-feed") -> Source:
    source = Source(
        tenant_id=tenant.id,
        type="rss",
        name="Demo feed",
        slug=slug,
        config={"url": FEED_URL},
        sensitivity="public",
        enabled=True,
    )
    session.add(source)
    await session.flush()
    return source


async def feed_items(session: AsyncSession, tenant: Tenant) -> list[Item]:
    stmt = select(Item).where(Item.tenant_id == tenant.id, Item.source == FEED_SOURCE)
    return list((await session.execute(stmt)).scalars().all())


async def poll_job(session: AsyncSession, tenant: Tenant, source: Source) -> Job:
    job_id = await queue.enqueue(
        session,
        tenant_id=tenant.id,
        kind=JobKind.POLL,
        payload={"source_id": str(source.id)},
    )
    job = await session.get(Job, job_id)
    assert job is not None
    return job


async def test_poll_ingests_entries_and_stores_the_http_cache_cursor(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    source = await make_source(db_session, tenant)

    result = await poll_source(db_session, source, transport=mock_transport(200))

    assert result.new_items == 2
    assert result.not_modified is False
    assert source.cursor == {"etag": ETAG, "last_modified": None}
    assert {item.source_ref for item in await feed_items(db_session, tenant)} == {"g-1", "g-2"}
    assert {item.hints["niche"] for item in await feed_items(db_session, tenant)} == {"news_radar"}


async def test_repoll_sends_the_stored_etag_and_a_304_ingests_nothing(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    source = await make_source(db_session, tenant)
    await poll_source(db_session, source, transport=mock_transport(200))
    sent: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(304)

    result = await poll_source(db_session, source, transport=httpx.MockTransport(recording))

    assert result.not_modified is True
    assert result.new_items == 0
    assert sent[0].headers["If-None-Match"] == ETAG
    count = await db_session.scalar(
        select(func.count()).select_from(Item).where(Item.tenant_id == tenant.id)
    )
    assert count == 2


async def test_handle_poll_records_a_failed_fetch_and_does_not_raise(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = await make_source(db_session, tenant)
    job = await poll_job(db_session, tenant, source)
    real_fetch: Fetch = poll_module.fetch_feed

    async def fetch_with_500(url: str, cursor: Any, **_: Any) -> poll_module.FetchResult:
        return await real_fetch(url, cursor, transport=mock_transport(500))

    monkeypatch.setattr(poll_module, "fetch_feed", fetch_with_500)

    await handle_poll(db_session, job)

    assert source.error_count == 1
    assert source.last_polled_at is not None
    assert await feed_items(db_session, tenant) == []


async def test_handle_poll_skips_disabled_sources(db_session: AsyncSession, tenant: Tenant) -> None:
    source = await make_source(db_session, tenant, slug="off")
    source.enabled = False
    job = await poll_job(db_session, tenant, source)

    await handle_poll(db_session, job)

    assert source.last_polled_at is None
    assert await feed_items(db_session, tenant) == []


async def test_scheduler_enqueues_once_per_due_source(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    source = await make_source(db_session, tenant, slug="due")
    now = utcnow()

    first = await enqueue_due_polls(db_session, now)
    second = await enqueue_due_polls(db_session, now)

    assert first == 1
    assert second == 0  # an open poll job already exists for this source
    jobs = (
        (
            await db_session.execute(
                select(Job).where(Job.tenant_id == tenant.id, Job.kind == JobKind.POLL.value)
            )
        )
        .scalars()
        .all()
    )
    assert [job.payload["source_id"] for job in jobs] == [str(source.id)]


async def test_scheduler_skips_a_source_polled_within_the_interval(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    source = await make_source(db_session, tenant, slug="fresh")
    source.last_polled_at = utcnow() - timedelta(minutes=1)

    assert await enqueue_due_polls(db_session, utcnow()) == 0


def test_entry_mapping_keeps_raw_link_but_drops_unsafe_hint_url() -> None:
    source = Source(
        tenant_id=uuid.uuid4(),
        type="rss",
        name="n",
        slug="s",
        config={},
        sensitivity="public",
        enabled=True,
    )
    entry = FeedEntry(
        ref="g-9", title="Odd link", link="javascript:alert(1)", summary="", published=None
    )

    body = entry_to_ingest(source, entry)

    assert body.source == FEED_SOURCE
    assert body.hints is not None
    assert body.hints.url is None
    assert body.hints.niche == "news_radar"
    assert body.payload["link"] == "javascript:alert(1)"  # raw kept (FR-06); hint is cut
