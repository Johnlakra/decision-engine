"""Hard per-tenant daily item cap: bulk never overshoots (FR-02, FR-07, NFR-05)."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Item, Tenant
from tests.integration.test_items_api import _app, _body, _key

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(db_session)), base_url="http://t"
    ) as c:
        yield c


async def _count(db_session: AsyncSession, tenant: Tenant) -> int:
    stmt = select(func.count()).select_from(Item).where(Item.tenant_id == tenant.id)
    return (await db_session.execute(stmt)).scalar_one()


async def test_bulk_inserts_exactly_the_remaining_quota(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    settings_env: pytest.MonkeyPatch,
) -> None:
    """FR-02: cap 5, 2 used -> bulk of 10 stores exactly 3, refuses 7 per row."""
    settings_env.setenv("ITEMS_PER_DAY", "5")
    get_settings.cache_clear()
    headers = await _key(db_session, tenant, ["items:write"])
    for i in range(2):
        created = await client.post("/v1/items", json=_body(f"p{i}"), headers=headers)
        assert created.status_code == 202

    response = await client.post(
        "/v1/items/bulk", json={"items": [_body(f"n{i}") for i in range(10)]}, headers=headers
    )

    rows: list[dict[str, Any]] = response.json()["results"]
    assert response.status_code == 207
    assert sum(1 for r in rows if r.get("id")) == 3
    assert sum(1 for r in rows if r.get("error") == "daily item cap reached") == 7
    assert await _count(db_session, tenant) == 5


async def test_idempotent_repeats_do_not_spend_quota(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    settings_env: pytest.MonkeyPatch,
) -> None:
    """FR-07: repeats in a bulk are free; remaining quota still goes to new rows."""
    settings_env.setenv("ITEMS_PER_DAY", "4")
    get_settings.cache_clear()
    headers = await _key(db_session, tenant, ["items:write"])
    for i in range(2):
        created = await client.post("/v1/items", json=_body(f"p{i}"), headers=headers)
        assert created.status_code == 202
    rows = [_body("p0"), _body("p1"), _body("n0"), _body("n1"), _body("n2")]

    response = await client.post("/v1/items/bulk", json={"items": rows}, headers=headers)

    results = response.json()["results"]
    assert [bool(r.get("id")) for r in results] == [True, True, True, True, False]
    assert await _count(db_session, tenant) == 4

    again = await client.post("/v1/items/bulk", json={"items": rows[:4]}, headers=headers)
    assert again.status_code == 207
    assert all(r.get("id") for r in again.json()["results"])
    assert await _count(db_session, tenant) == 4
