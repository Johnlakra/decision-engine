"""GET /v1/stats/today (FR-60, FR-64 read side)."""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rate_limiter
from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import get_session
from app.llm.config import load_config
from app.main import create_app
from app.models import Decision, Item, LlmUsage, Tenant
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.integration

YESTERDAY = timedelta(days=1, hours=1)


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


@pytest_asyncio.fixture
async def reader(db_session: AsyncSession, tenant: Tenant) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    key = await create_api_key(db_session, tenant.id, "t", ["items:read"], pepper)
    return {"Authorization": f"Bearer {key}"}


async def _item(
    session: AsyncSession, tenant: Tenant, ref: str, *, age: timedelta | None = None, **fields: Any
) -> Item:
    item = Item(tenant_id=tenant.id, source="manual", source_ref=ref, raw={}, **fields)
    if age is not None:
        item.created_at = utcnow() - age
    session.add(item)
    await session.flush()
    return item


async def _decision(
    session: AsyncSession, tenant: Tenant, item: Item, by: str, **fields: Any
) -> None:
    session.add(
        Decision(tenant_id=tenant.id, item_id=item.id, verdict="approve", decided_by=by, **fields)
    )
    await session.flush()


async def test_requires_reader_scope(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    assert (await client.get("/v1/stats/today")).status_code == 401
    pepper = get_settings().api_key_pepper.get_secret_value()
    key = await create_api_key(db_session, tenant.id, "w", ["items:write"], pepper)
    resp = await client.get("/v1/stats/today", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 403


async def test_empty_tenant_is_all_zero_with_null_agreement(
    client: httpx.AsyncClient, reader: dict[str, str]
) -> None:
    resp = await client.get("/v1/stats/today", headers=reader)
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == utcnow().date().isoformat()
    assert (body["items_in"], body["decided"], body["auto_handled"], body["discarded"]) == (0,) * 4
    assert body["by_status"] == {} and body["by_niche"] == {}
    assert body["llm"] == [] or all(row["requests_used"] == 0 for row in body["llm"])
    assert body["laya_agreement"] is None


async def test_counts_cover_the_utc_day_and_this_tenant_only(
    client: httpx.AsyncClient, reader: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    other = Tenant(name="Other")
    db_session.add(other)
    await db_session.flush()
    a = await _item(db_session, tenant, "a", status="awaiting_approval", niche="inbox")
    b = await _item(db_session, tenant, "b", status="done", niche="inbox")
    c = await _item(db_session, tenant, "c", status="discarded")
    await _item(db_session, tenant, "old", age=YESTERDAY, status="done")
    old_discard = await _item(db_session, tenant, "old-d", age=YESTERDAY, status="discarded")
    old_discard.updated_at = utcnow() - YESTERDAY
    await _item(db_session, other, "theirs", status="done")
    await _decision(db_session, tenant, b, "human")
    await _decision(db_session, tenant, a, "human", undone_at=utcnow())  # undone: not counted
    await _decision(db_session, tenant, c, "auto")
    await _decision(db_session, tenant, c, "llm")
    await db_session.flush()

    body = (await client.get("/v1/stats/today", headers=reader)).json()

    assert body["items_in"] == 3
    assert body["decided"] == 1
    assert body["auto_handled"] == 1
    assert body["discarded"] == 1
    assert body["by_status"] == {"awaiting_approval": 1, "done": 1, "discarded": 1}
    assert body["by_niche"] == {"inbox": 2, "unassigned": 1}


async def test_old_decisions_are_not_counted(
    client: httpx.AsyncClient, reader: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    item = await _item(db_session, tenant, "x", status="done")
    await _decision(db_session, tenant, item, "human")
    db_session.add(
        Decision(
            tenant_id=tenant.id,
            item_id=item.id,
            verdict="reject",
            decided_by="human",
            created_at=utcnow() - YESTERDAY,
        )
    )
    await db_session.flush()
    body = (await client.get("/v1/stats/today", headers=reader)).json()
    assert body["decided"] == 1


async def test_llm_usage_per_provider_with_limits(
    client: httpx.AsyncClient, reader: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    rows = [
        ("gemini", 100, 20),
        ("gemini", 50, 10),
        ("groq", 10, 5),
    ]
    for provider, prompt, completion in rows:
        db_session.add(
            LlmUsage(
                tenant_id=tenant.id,
                provider=provider,
                model="m",
                purpose="classify",
                prompt_tokens=prompt,
                completion_tokens=completion,
            )
        )
    db_session.add(
        LlmUsage(
            tenant_id=tenant.id,
            provider="gemini",
            model="m",
            purpose="x",
            prompt_tokens=999,
            created_at=utcnow() - YESTERDAY,
        )  # fmt: skip
    )
    await db_session.flush()

    body = (await client.get("/v1/stats/today", headers=reader)).json()

    by_provider = {row["provider"]: row for row in body["llm"]}
    assert by_provider["gemini"]["requests_used"] == 2
    assert by_provider["gemini"]["tokens_used"] == 180
    assert by_provider["groq"]["requests_used"] == 1 and by_provider["groq"]["tokens_used"] == 15
    config = load_config().providers
    assert by_provider["gemini"]["requests_limit"] == config["gemini"].rpd
    assert by_provider["groq"]["tokens_limit"] == config["groq"].tpd
    assert set(by_provider["gemini"]) == {
        "provider", "requests_used", "requests_limit", "tokens_used", "tokens_limit",
    }  # fmt: skip


def _triage(own: dict[str, str], shadow: dict[str, str] | None) -> dict[str, Any]:
    def answers(choices: dict[str, str]) -> dict[str, Any]:
        return {
            q: {"type": "choice", "choice": c, "source": "llm_fallback"} for q, c in choices.items()
        }

    record: dict[str, Any] = {
        "mode": "shadow",
        "decided_by": "llm_fallback",
        "answers": answers(own),
    }
    if shadow is not None:
        record["shadow"] = {"answers": answers(shadow)}
    return record


async def test_laya_agreement_uses_shadow_answers_only(
    client: httpx.AsyncClient, reader: dict[str, str], db_session: AsyncSession, tenant: Tenant
) -> None:
    both = {"niche": "inbox", "risk": "none"}
    await _item(db_session, tenant, "s1", triage=_triage(both, both))
    await _item(db_session, tenant, "s2", triage=_triage({"niche": "inbox"}, {"niche": "generic"}))
    await _item(db_session, tenant, "no-shadow", triage=_triage({"niche": "inbox"}, None))
    old = _triage({"niche": "inbox"}, {"niche": "generic"})
    await _item(db_session, tenant, "old", age=YESTERDAY, triage=old)
    body = (await client.get("/v1/stats/today", headers=reader)).json()
    assert body["laya_agreement"] == pytest.approx(2 / 3)
