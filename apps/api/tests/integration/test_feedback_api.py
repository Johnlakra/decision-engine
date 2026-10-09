"""GET /v1/feedback/export (FR-80)."""

import json

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Feedback, Tenant
from tests.integration.graph_support import bearer, make_item

pytestmark = pytest.mark.integration

QUESTIONS = {"needs_decision": {"options": ["yes", "no"]}}
GOLD = {"answers": {"needs_decision": {"yes": 0.9, "no": 0.1}}}


async def _seed(factory: async_sessionmaker[AsyncSession], tenant: Tenant) -> None:
    async with factory() as session:
        for niche in ("generic", "inbox"):
            item_id = await make_item(factory, tenant, subscribe=False, niche=niche)
            session.add(
                Feedback(
                    tenant_id=tenant.id,
                    item_id=item_id,
                    kind="decision",
                    niche=niche,
                    state_text=f"state {niche}",
                    questions=QUESTIONS,
                    gold=GOLD,
                )
            )
        await session.commit()


async def test_export_streams_ndjson(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
    admin_key: str,
) -> None:
    await _seed(committed_db, tenant_committed)
    response = await api_client.get(
        "/v1/feedback/export?niche=inbox&format=laya_eval", headers=bearer(admin_key)
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert len(lines) == 1
    assert lines[0]["expected"] == {"needs_decision": "yes"}
    assert "raw" not in lines[0]


async def test_export_default_format_is_train(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
    admin_key: str,
) -> None:
    await _seed(committed_db, tenant_committed)
    response = await api_client.get("/v1/feedback/export", headers=bearer(admin_key))
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert len(rows) == 2 and all("gold" in r for r in rows)


async def test_export_rejects_unknown_format(api_client: httpx.AsyncClient, admin_key: str) -> None:
    response = await api_client.get("/v1/feedback/export?format=csv", headers=bearer(admin_key))
    assert response.status_code == 422


async def test_export_requires_auth(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/v1/feedback/export")).status_code == 401
