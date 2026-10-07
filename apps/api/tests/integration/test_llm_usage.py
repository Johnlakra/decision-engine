"""llm_usage rows and the Postgres budget fallback against a real database (FR-62, FR-60)."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import gateway, providers, usage
from app.llm.budgets import PostgresBudgetStore, set_budget_store
from app.llm.errors import ProviderError
from app.models import Item, Tenant
from app.models.llm_usage import LlmUsage
from tests.fakes.fake_llm import FakeProviderCall
from tests.unit.llm.conftest import make_config

pytestmark = pytest.mark.integration


def factory_for(session: AsyncSession) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        yield session

    return _open


@pytest.fixture(autouse=True)
def _fresh_tenant_cache() -> None:
    usage.reset_tenant_cache()


async def rows(session: AsyncSession) -> list[LlmUsage]:
    return list((await session.execute(select(LlmUsage))).scalars())


async def test_estimate_cost_is_zero_for_free_and_priced_for_paid() -> None:
    config = make_config(gemini_api_key="g", openai_api_key="k", openai_model="openai/m")
    assert usage.estimate_cost_inr(config.providers["gemini"], 1000, 1000) == Decimal("0")
    paid = usage.estimate_cost_inr(config.providers["openai"], 1_000_000, 1_000_000)
    assert paid == Decimal("198.0000")  # 22 + 176 INR per 1M each


async def test_record_usage_writes_row_with_cost_and_item(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    item = Item(tenant_id=tenant.id, source="email", source_ref="m1", raw={})
    db_session.add(item)
    await db_session.flush()
    config = make_config(openai_api_key="k", openai_model="openai/m")
    await usage.record_usage(
        factory_for(db_session),
        provider=config.providers["openai"],
        purpose="decide",
        item_id=str(item.id),
        prompt_tokens=2000,
        completion_tokens=1000,
        latency_ms=321,
        ok=True,
        error_code=None,
    )
    [row] = await rows(db_session)
    assert (row.provider, row.model, row.purpose, row.item_id) == (
        "openai",
        "openai/m",
        "decide",
        item.id,
    )
    assert row.tenant_id == tenant.id and row.latency_ms == 321 and row.ok
    assert row.cost_inr == Decimal("0.2200")  # 2000*22/1e6 + 1000*176/1e6


async def test_record_usage_never_raises_without_tenant(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(gemini_api_key="g")
    await db_session.execute(Tenant.__table__.delete())  # type: ignore[attr-defined]
    await usage.record_usage(
        factory_for(db_session),
        provider=config.providers["gemini"],
        purpose="p",
        item_id="not-a-uuid",
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=1,
        ok=True,
        error_code=None,
    )
    assert await rows(db_session) == []


async def test_postgres_store_counts_todays_rows_per_provider(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    config = make_config(gemini_api_key="g", groq_api_key="q")
    for name in ("gemini", "gemini", "groq"):
        await usage.record_usage(
            factory_for(db_session),
            provider=config.providers[name],
            purpose="x",
            item_id=None,
            prompt_tokens=1,
            completion_tokens=1,
            latency_ms=1,
            ok=True,
            error_code=None,
        )
    store = PostgresBudgetStore(factory_for(db_session))
    assert await store.count("gemini") == 2
    assert await store.count("groq") == 1
    assert await store.count("cerebras") == 0
    tomorrow = PostgresBudgetStore(
        factory_for(db_session),
        clock=lambda: datetime.now(UTC).replace(year=datetime.now(UTC).year + 1),
    )
    assert await tomorrow.count("gemini") == 0


async def test_postgres_store_cooldown_is_in_memory() -> None:
    store = PostgresBudgetStore(factory_for(None))  # type: ignore[arg-type]
    await store.cool_down("gemini", 60)
    assert await store.is_cooling("gemini")
    assert not await store.is_cooling("groq")


async def test_gateway_logs_every_attempt_and_budget_uses_the_rows(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = make_config(gemini_api_key="g", groq_api_key="q", gemini_rpd=1)
    monkeypatch.setattr(gateway, "load_config", lambda: config)
    monkeypatch.setattr(gateway, "session_factory", factory_for(db_session))
    set_budget_store(PostgresBudgetStore(factory_for(db_session)))
    fake = FakeProviderCall()
    fake.script("gemini", ProviderError("rate_limit"))
    fake.script("groq", "one", "two")
    monkeypatch.setattr(providers, "call", fake)
    try:
        assert await gateway.complete_text("decide", [], sensitivity="public") == "one"
        # gemini rpd=1 is spent by its failed attempt: the second call skips it.
        assert await gateway.complete_text("decide", [], sensitivity="public") == "two"
    finally:
        set_budget_store(None)
    assert fake.called == ["gemini", "groq", "groq"]
    got = sorted((r.provider, r.ok, r.error_code, r.item_id) for r in await rows(db_session))
    assert got == [
        ("gemini", False, "rate_limit", None),
        ("groq", True, None, None),
        ("groq", True, None, None),
    ]
