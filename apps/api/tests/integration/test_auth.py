"""Auth dependency, scopes, rate limit and /health against a real DB (FR-07, FR-111, NFR-05)."""

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_principal, get_rate_limiter, require_scope
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.errors import install_problem_handlers
from app.db.session import get_session
from app.models import ApiKey, Tenant
from app.security.api_keys import Principal, authenticate, create_api_key
from app.security.rate_limit import MemoryRateLimiter, RedisRateLimiter, ResilientRateLimiter

pytestmark = pytest.mark.integration


class BrokenRedis:
    async def incr(self, name: str) -> int:
        raise ConnectionError("redis down")

    async def expire(self, name: str, time: int) -> bool:
        raise ConnectionError("redis down")


def _pepper() -> str:
    return get_settings().api_key_pepper.get_secret_value()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(health_router)

    @app.get("/who")
    async def who(p: Annotated[Principal, Depends(get_principal)]) -> dict[str, str]:
        return {"tenant_id": str(p.tenant_id)}

    @app.get("/write")
    async def write(
        _: Annotated[Principal, Depends(require_scope("items:write"))],
    ) -> dict[str, bool]:
        return {"ok": True}

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.state.limiter = limiter
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        http.app = app  # type: ignore[attr-defined]
        yield http


async def _key(session: AsyncSession, tenant: Tenant, scopes: list[str]) -> str:
    return await create_api_key(session, tenant.id, "test", scopes, _pepper())


def _auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def test_health_needs_no_auth_or_db(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}


async def test_valid_key_authenticates(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    key = await _key(db_session, tenant, ["items:read"])
    resp = await client.get("/who", headers=_auth(key))
    assert resp.status_code == 200 and resp.json()["tenant_id"] == str(tenant.id)


async def test_wrong_secret_unknown_prefix_and_malformed_are_401(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    key = await _key(db_session, tenant, ["admin"])
    prefix = key.split("_", 2)[1]
    for bad in (f"de_{prefix}_wrong", "de_00000000_whatever", "garbage", "de_x"):
        resp = await client.get("/who", headers=_auth(bad))
        assert resp.status_code == 401, bad
        assert resp.headers["content-type"].startswith("application/problem+json")
    assert (await client.get("/who")).status_code == 401
    assert (await client.get("/who", headers={"Authorization": f"Basic {key}"})).status_code == 401


async def test_revoked_key_is_401(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    key = await _key(db_session, tenant, ["admin"])
    await db_session.execute(text("update api_keys set revoked_at = now()"))
    assert (await client.get("/who", headers=_auth(key))).status_code == 401


async def test_missing_scope_403_and_admin_implies_all(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    reader = await _key(db_session, tenant, ["items:read"])
    writer = await _key(db_session, tenant, ["items:write"])
    admin = await _key(db_session, tenant, ["admin"])
    denied = await client.get("/write", headers=_auth(reader))
    assert denied.status_code == 403
    assert denied.headers["content-type"].startswith("application/problem+json")
    assert (await client.get("/write", headers=_auth(writer))).status_code == 200
    assert (await client.get("/write", headers=_auth(admin))).status_code == 200


async def test_key_never_stored_or_logged_in_plain_text(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    key = await _key(db_session, tenant, ["admin"])
    secret = key.split("_", 2)[2]
    await client.get("/who", headers=_auth(key))
    await client.get("/who", headers=_auth(key + "x"))
    row = await db_session.scalar(select(ApiKey))
    assert row is not None
    stored = " ".join([row.hash, row.prefix, row.name, *row.scopes])
    assert secret not in stored and key not in stored
    assert secret not in caplog.text and key not in caplog.text


async def test_last_used_updated_at_most_once_a_minute(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    key = await _key(db_session, tenant, ["admin"])
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    await authenticate(db_session, key, _pepper(), now=t0)
    await authenticate(db_session, key, _pepper(), now=t0 + timedelta(seconds=30))
    row = await db_session.scalar(select(ApiKey))
    assert row is not None and row.last_used_at == t0
    await authenticate(db_session, key, _pepper(), now=t0 + timedelta(seconds=61))
    await db_session.refresh(row)
    assert row.last_used_at == t0 + timedelta(seconds=61)


async def test_rate_limit_429_with_retry_after(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "2")
    get_settings.cache_clear()
    try:
        key = await _key(db_session, tenant, ["admin"])
        codes = [(await client.get("/who", headers=_auth(key))).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        resp = await client.get("/who", headers=_auth(key))
        assert resp.headers["content-type"].startswith("application/problem+json")
        assert 1 <= int(resp.headers["retry-after"]) <= 60
    finally:
        get_settings.cache_clear()


async def test_redis_error_falls_back_to_memory_and_still_limits(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    get_settings.cache_clear()
    limiter = ResilientRateLimiter(RedisRateLimiter(BrokenRedis()), MemoryRateLimiter())
    client.app.dependency_overrides[get_rate_limiter] = lambda: limiter  # type: ignore[attr-defined]
    try:
        key = await _key(db_session, tenant, ["admin"])
        assert (await client.get("/who", headers=_auth(key))).status_code == 200
        assert (await client.get("/who", headers=_auth(key))).status_code == 429
    finally:
        get_settings.cache_clear()
