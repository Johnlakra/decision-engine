"""Per-tenant daily cap on POST /v1/decide (code review M3; FR-35, NFR-05)."""

import asyncio

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.triage.service as triage_service
from alembic import command
from app.core.config import get_settings
from app.models import Tenant
from app.security.api_keys import create_api_key
from tests.conftest import alembic_config
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import fake_llm  # noqa: F401
from tests.integration.graph_support import (
    bearer,
    mini_client,  # noqa: F401
    real_niches,  # noqa: F401
)
from tests.integration.test_decide_api import QUESTIONS

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]
BODY = {"state": "wheat 2200", "questions": QUESTIONS}


async def _decide_key(factory: SessionFactory, tenant: Tenant, name: str) -> str:
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with factory() as session:
        key = await create_api_key(session, tenant.id, name, ["decide"], pepper)
        await session.commit()
        return key


async def _second_tenant_key(factory: SessionFactory) -> str:
    async with factory() as session:
        other = Tenant(name="Other Tenant")
        session.add(other)
        await session.commit()
    return await _decide_key(factory, other, "other")


async def test_limit_plus_one_call_is_429_with_retry_after(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage_service, "get_laya_client", lambda: FakeLayaClient())
    monkeypatch.setenv("DECIDE_DAILY_LIMIT_PER_TENANT", "2")
    get_settings.cache_clear()
    key = await _decide_key(committed_db, tenant_committed, "d")

    first = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key))
    second = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key))
    third = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key))

    assert (first.status_code, second.status_code) == (200, 200)
    assert third.status_code == 429
    assert 0 < int(third.headers["Retry-After"]) <= 86_400
    assert third.headers["content-type"].startswith("application/problem+json")
    assert third.json()["type"].endswith("daily-decide-cap")


async def test_counter_is_per_tenant(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage_service, "get_laya_client", lambda: FakeLayaClient())
    monkeypatch.setenv("DECIDE_DAILY_LIMIT_PER_TENANT", "1")
    get_settings.cache_clear()
    key_a = await _decide_key(committed_db, tenant_committed, "a")
    key_b = await _second_tenant_key(committed_db)

    a_first = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key_a))
    a_second = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key_a))
    b_first = await mini_client.post("/v1/decide", json=BODY, headers=bearer(key_b))

    assert (a_first.status_code, a_second.status_code, b_first.status_code) == (200, 429, 200)


async def test_concurrent_calls_never_exceed_limit(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(triage_service, "get_laya_client", lambda: FakeLayaClient())
    monkeypatch.setenv("DECIDE_DAILY_LIMIT_PER_TENANT", "3")
    get_settings.cache_clear()
    key = await _decide_key(committed_db, tenant_committed, "c")

    responses = await asyncio.gather(
        *(mini_client.post("/v1/decide", json=BODY, headers=bearer(key)) for _ in range(8))
    )

    assert sorted(r.status_code for r in responses) == [200] * 3 + [429] * 5


async def test_migration_0003_reversible(migrated_db: str) -> None:
    config = alembic_config()
    sql = "SELECT to_regclass('decide_usage') IS NOT NULL"

    async def exists() -> bool:
        engine = create_async_engine(migrated_db)
        try:
            async with engine.connect() as conn:
                return bool((await conn.execute(text(sql))).scalar_one())
        finally:
            await engine.dispose()

    assert await exists()
    await asyncio.to_thread(command.downgrade, config, "0002")
    assert not await exists()
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await exists()
