"""/health/deep (NFR-08)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import health as health_mod
from app.api.deps import get_rate_limiter
from app.api.health import get_probe_session
from app.core.config import get_settings
from app.db.session import get_session
from app.llm import gateway
from app.main import create_app
from app.models import Tenant
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter
from tests.fakes.fake_laya import FakeLayaClient

pytestmark = pytest.mark.integration


class BrokenSession:
    async def execute(self, *args: object, **kwargs: object) -> None:
        raise ConnectionError("db down")


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    app.state.laya = FakeLayaClient()

    async def ok_ping(provider: str | None = None) -> dict[str, str]:
        return {"gemini": "skipped"}

    async def no_redis() -> str:
        return "skipped"

    monkeypatch.setattr(gateway, "ping", ok_ping)
    monkeypatch.setattr(health_mod, "ping_redis", no_redis)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        http.app = app  # type: ignore[attr-defined]
        yield http


async def _headers(session: AsyncSession, tenant: Tenant) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    key = await create_api_key(session, tenant.id, "t", ["items:read"], pepper)
    return {"Authorization": f"Bearer {key}"}


async def test_deep_requires_key(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/deep")).status_code == 401


async def test_deep_ok_shape(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    resp = await client.get("/health/deep", headers=await _headers(db_session, tenant))
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == "ok" and body["db"] == "ok" and body["laya"] == "ok"
    assert body["llm"] == {"gemini": "skipped"}
    assert body["niches"]["loaded"] >= 1 and body["niches"]["errors"] == []
    assert isinstance(body["queue_depth"], int) and "oldest_job_age_s" in body


async def test_laya_down_is_degraded(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    client.app.state.laya = FakeLayaClient(fail=True)  # type: ignore[attr-defined]
    resp = await client.get("/health/deep", headers=await _headers(db_session, tenant))
    assert resp.status_code == 200
    assert resp.json()["laya"] == "down" and resp.json()["status"] == "degraded"


async def test_no_laya_and_no_llm_key_are_skipped_not_degraded(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    client.app.state.laya = None  # type: ignore[attr-defined]
    resp = await client.get("/health/deep", headers=await _headers(db_session, tenant))
    assert resp.json()["laya"] == "skipped" and resp.json()["status"] == "ok"


async def test_llm_cooldown_is_degraded(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def cooling(provider: str | None = None) -> dict[str, str]:
        return {"gemini": "cooldown"}

    monkeypatch.setattr(gateway, "ping", cooling)
    resp = await client.get("/health/deep", headers=await _headers(db_session, tenant))
    assert resp.json()["status"] == "degraded"


async def test_db_down_is_503(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _headers(db_session, tenant)

    async def broken() -> BrokenSession:
        return BrokenSession()

    client.app.dependency_overrides[get_probe_session] = broken  # type: ignore[attr-defined]
    resp = await client.get("/health/deep", headers=headers)
    assert resp.status_code == 503
    assert resp.json()["db"] == "down" and resp.json()["status"] == "degraded"
    assert "db down" not in resp.text
