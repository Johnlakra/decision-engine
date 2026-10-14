"""GET/POST /v1/sources and PATCH /v1/sources/{id} (FR-90, ADR 0010)."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rate_limiter
from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import get_session
from app.main import create_app
from app.models import Item, Source, Tenant
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.integration

VALID_RSS: dict[str, Any] = {
    "type": "rss",
    "name": "Example feed",
    "slug": "example-feed",
    "config": {"url": "https://example.com/feed.xml"},
    "niche_hint": "news_radar",
}
OUT_KEYS = {
    "id", "type", "name", "slug", "enabled", "niche_hint", "last_polled_at", "error_count",
    "items_today",
}  # fmt: skip


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


async def _headers(session: AsyncSession, tenant: Tenant, scopes: list[str]) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    key = await create_api_key(session, tenant.id, "t", scopes, pepper)
    return {"Authorization": f"Bearer {key}"}


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession, tenant: Tenant) -> dict[str, str]:
    return await _headers(db_session, tenant, ["admin"])


async def _add_source(db_session: AsyncSession, tenant: Tenant, **fields: Any) -> Source:
    values: dict[str, Any] = {
        "type": "rss",
        "name": "Seed",
        "slug": "seed-feed",
        "config": {"url": "https://example.com/seed.xml"},
        "sensitivity": "public",
    }
    row = Source(tenant_id=tenant.id, **{**values, **fields})
    db_session.add(row)
    await db_session.flush()
    return row


# ---- GET --------------------------------------------------------------------------------------


async def test_list_requires_reader_scope(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    assert (await client.get("/v1/sources")).status_code == 401
    writer = await _headers(db_session, tenant, ["items:write"])
    assert (await client.get("/v1/sources", headers=writer)).status_code == 403


async def test_list_shape_never_leaks_secrets_and_scopes_to_tenant(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    other = Tenant(name="Other")
    db_session.add(other)
    await db_session.flush()
    row = await _add_source(
        db_session, tenant, secret_enc="SECRET", oauth_enc="OAUTH", config={"url": "https://x.io/f"}
    )
    await _add_source(db_session, other, slug="their-feed")
    headers = await _headers(db_session, tenant, ["items:read"])
    resp = await client.get("/v1/sources", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [d["slug"] for d in data] == ["seed-feed"]
    assert set(data[0]) == OUT_KEYS
    assert data[0]["id"] == str(row.id) and data[0]["enabled"] is True
    assert "SECRET" not in resp.text and "OAUTH" not in resp.text and "x.io" not in resp.text


async def test_items_today_counts_feed_items_of_this_utc_day(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    await _add_source(db_session, tenant)
    yesterday = utcnow() - timedelta(days=1, hours=1)
    rows = [
        ("a", "seed-feed", None),
        ("b", "seed-feed", None),
        ("c", "seed-feed", yesterday),
        ("d", "other-feed", None),
    ]
    for ref, feed, created in rows:
        item = Item(tenant_id=tenant.id, source="rss", source_ref=ref, raw={"feed": feed})
        if created is not None:
            item.created_at = created
        db_session.add(item)
    await db_session.flush()
    headers = await _headers(db_session, tenant, ["items:read"])
    data = (await client.get("/v1/sources", headers=headers)).json()["data"]
    assert data[0]["items_today"] == 2


# ---- POST -------------------------------------------------------------------------------------


async def test_post_requires_admin(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    reader = await _headers(db_session, tenant, ["items:read", "items:write"])
    assert (await client.post("/v1/sources", headers=reader, json=VALID_RSS)).status_code == 403


async def test_post_rss_creates_enabled_public_source(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    resp = await client.post("/v1/sources", headers=admin, json=VALID_RSS)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body) == OUT_KEYS
    assert body["slug"] == "example-feed" and body["enabled"] is True
    assert body["items_today"] == 0 and body["error_count"] == 0 and body["last_polled_at"] is None
    assert body["niche_hint"] == "news_radar"
    row = await db_session.scalar(select(Source).where(Source.slug == "example-feed"))
    assert row is not None
    assert row.config == {"url": "https://example.com/feed.xml"}
    assert row.sensitivity == "public" and row.secret_enc is None


async def test_post_google_news(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    body = {
        "type": "google_news",
        "name": "News on rice",
        "slug": "rice-news",
        "config": {"query": "punjab rice msp"},
    }
    resp = await client.post("/v1/sources", headers=admin, json=body)
    assert resp.status_code == 201 and resp.json()["niche_hint"] is None


async def test_duplicate_slug_is_409_problem(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    assert (await client.post("/v1/sources", headers=admin, json=VALID_RSS)).status_code == 201
    resp = await client.post("/v1/sources", headers=admin, json=VALID_RSS)
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")
    count = await db_session.scalar(
        select(func.count(Source.id)).where(Source.slug == "example-feed")
    )
    assert count == 1


async def test_same_slug_in_another_tenant_is_allowed(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    other = Tenant(name="Other")
    db_session.add(other)
    await db_session.flush()
    await _add_source(db_session, other, slug="example-feed")
    assert (await client.post("/v1/sources", headers=admin, json=VALID_RSS)).status_code == 201


@pytest.mark.parametrize("kind", ["gmail", "instagram", "webhook", "telegram", "hn", "csv"])
async def test_other_types_are_422_not_available(
    client: httpx.AsyncClient, admin: dict[str, str], kind: str
) -> None:
    resp = await client.post("/v1/sources", headers=admin, json={**VALID_RSS, "type": kind})
    assert resp.status_code == 422
    assert "not available yet" in resp.text


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/feed.xml",
        "ftp://example.com/feed.xml",
        "https://user:pw@example.com/feed.xml",
        "https:///nohost",
        "https://127.0.0.1/feed.xml",
        "https://10.0.0.5/feed.xml",
        "javascript:alert(1)",
        "not a url",
        "",
    ],
)
async def test_rss_url_must_be_https_and_public(
    client: httpx.AsyncClient, admin: dict[str, str], url: str
) -> None:
    body = {**VALID_RSS, "config": {"url": url}}
    resp = await client.post("/v1/sources", headers=admin, json=body)
    assert resp.status_code == 422, url


@pytest.mark.parametrize(
    "body",
    [
        {**VALID_RSS, "slug": "Bad_Slug"},
        {**VALID_RSS, "slug": "x"},
        {**VALID_RSS, "name": ""},
        {**VALID_RSS, "niche_hint": "Not A Niche"},
        {**VALID_RSS, "config": {}},
        {**VALID_RSS, "config": {"url": "https://example.com/f", "extra": 1}},
        {**VALID_RSS, "config": {"query": "x"}},
        {**VALID_RSS, "extra_key": 1},
        {"type": "google_news", "name": "n", "slug": "gn-one", "config": {"query": ""}},
        {"type": "google_news", "name": "n", "slug": "gn-one", "config": {"query": "x" * 201}},
        {"type": "google_news", "name": "n", "slug": "gn-one", "config": {"url": "https://a.io"}},
    ],
)
async def test_invalid_bodies_are_422(
    client: httpx.AsyncClient, admin: dict[str, str], body: dict[str, Any]
) -> None:
    resp = await client.post("/v1/sources", headers=admin, json=body)
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")


# ---- PATCH ------------------------------------------------------------------------------------


async def test_patch_toggles_both_ways_and_keeps_state(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    row = await _add_source(
        db_session, tenant, error_count=3, cursor={"etag": "abc"}, last_polled_at=utcnow()
    )
    resp = await client.patch(f"/v1/sources/{row.id}", headers=admin, json={"enabled": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == OUT_KEYS and body["enabled"] is False and body["error_count"] == 3
    await db_session.refresh(row)
    assert row.enabled is False and row.cursor == {"etag": "abc"} and row.error_count == 3
    back = await client.patch(f"/v1/sources/{row.id}", headers=admin, json={"enabled": True})
    assert back.json()["enabled"] is True


async def test_patch_same_value_is_200_without_a_write(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    row = await _add_source(db_session, tenant)
    stamp = row.updated_at
    for _ in range(2):
        resp = await client.patch(f"/v1/sources/{row.id}", headers=admin, json={"enabled": True})
        assert resp.status_code == 200 and resp.json()["enabled"] is True
    await db_session.refresh(row)
    assert row.updated_at == stamp


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"enabled": False, "name": "x"},
        {"enabled": False, "config": {"url": "https://evil.example"}},
        {"enabled": False, "error_count": 0},
        {"enabled": False, "cursor": None},
        {"enabled": False, "sensitivity": "public"},
        {"name": "x"},
        {"enabled": "maybe"},
        {"enabled": None},
    ],
)
async def test_patch_other_keys_are_422(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    db_session: AsyncSession,
    tenant: Tenant,
    body: dict[str, Any],
) -> None:
    row = await _add_source(db_session, tenant)
    resp = await client.patch(f"/v1/sources/{row.id}", headers=admin, json=body)
    assert resp.status_code == 422
    await db_session.refresh(row)
    assert row.enabled is True and row.name == "Seed"


async def test_patch_unknown_or_foreign_source_is_404(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    other = Tenant(name="Other")
    db_session.add(other)
    await db_session.flush()
    foreign = await _add_source(db_session, other, slug="their-feed")
    for target in (foreign.id, uuid.uuid4()):
        resp = await client.patch(f"/v1/sources/{target}", headers=admin, json={"enabled": False})
        assert resp.status_code == 404
    await db_session.refresh(foreign)
    assert foreign.enabled is True


async def test_patch_requires_admin_and_uuid(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant, admin: dict[str, str]
) -> None:
    row = await _add_source(db_session, tenant)
    reader = await _headers(db_session, tenant, ["items:read", "items:write"])
    assert (
        await client.patch(f"/v1/sources/{row.id}", headers=reader, json={"enabled": False})
    ).status_code == 403
    assert (
        await client.patch("/v1/sources/not-a-uuid", headers=admin, json={"enabled": False})
    ).status_code == 422
