"""Per-tenant daily item cap edge rules (FR-02, FR-03, FR-07, ADR 0004)."""

from collections.abc import AsyncIterator
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utcnow
from app.models import Item, Tenant
from tests.integration.test_items_api import _app, _body, _key

pytestmark = pytest.mark.integration
SECONDS_PER_DAY = 86_400


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(db_session))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


@pytest.fixture
def cap_two(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("ITEMS_PER_DAY", "2")
    get_settings.cache_clear()


async def _fill(client: httpx.AsyncClient, headers: dict[str, str], count: int = 2) -> None:
    for i in range(count):
        response = await client.post("/v1/items", json=_body(f"f{i}"), headers=headers)
        assert response.status_code == 202


@pytest.mark.usefixtures("cap_two")
async def test_cap_is_per_tenant(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    other = Tenant(name="Other")
    db_session.add(other)
    await db_session.flush()
    mine = await _key(db_session, tenant, ["items:write"])
    theirs = await _key(db_session, other, ["items:write"])
    await _fill(client, mine)

    assert (await client.post("/v1/items", json=_body("x"), headers=mine)).status_code == 429
    assert (await client.post("/v1/items", json=_body("x"), headers=theirs)).status_code == 202


@pytest.mark.usefixtures("cap_two")
async def test_retry_after_points_at_next_utc_midnight(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)

    response = await client.post("/v1/items", json=_body("x"), headers=headers)

    assert response.status_code == 429
    assert 1 <= int(response.headers["Retry-After"]) <= SECONDS_PER_DAY
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.usefixtures("cap_two")
async def test_yesterdays_items_do_not_count(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)
    await db_session.execute(
        update(Item).values(created_at=utcnow() - timedelta(days=1, minutes=1))
    )

    assert (await client.post("/v1/items", json=_body("new"), headers=headers)).status_code == 202


@pytest.mark.usefixtures("cap_two")
async def test_bulk_over_cap_is_429_with_retry_after(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)

    response = await client.post("/v1/items/bulk", json={"items": [_body("b")]}, headers=headers)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


@pytest.mark.usefixtures("cap_two")
async def test_repeat_of_stored_item_at_cap_is_still_200(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)

    repeat = await client.post("/v1/items", json=_body("f0"), headers=headers)

    assert repeat.status_code == 200


@pytest.mark.usefixtures("cap_two")
async def test_bulk_of_only_stored_items_at_cap_is_207_not_429(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)

    response = await client.post(
        "/v1/items/bulk", json={"items": [_body("f0"), _body("f1")]}, headers=headers
    )

    assert response.status_code == 207
    assert all(row.get("id") for row in response.json()["results"])


@pytest.mark.usefixtures("cap_two")
async def test_bulk_at_cap_returns_stored_rows_and_refuses_new_ones(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    await _fill(client, headers)

    response = await client.post(
        "/v1/items/bulk", json={"items": [_body("f0"), _body("new")]}, headers=headers
    )

    assert response.status_code == 207
    first, second = response.json()["results"]
    assert first["id"] and second["error"] == "daily item cap reached"
