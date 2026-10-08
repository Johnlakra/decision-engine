"""Items API against a real DB (FR-01, FR-02, FR-03, FR-06, FR-07)."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rate_limiter
from app.api.v1.items import router
from app.core.config import get_settings
from app.core.errors import install_problem_handlers
from app.db.session import get_session
from app.models import Item, Job, Tenant
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.integration


def _app(db_session: AsyncSession) -> FastAPI:
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(router, prefix="/v1")

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    return app


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_app(db_session))
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def _key(db_session: AsyncSession, tenant: Tenant, scopes: list[str]) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    full = await create_api_key(db_session, tenant.id, "k", scopes, pepper)
    return {"Authorization": f"Bearer {full}"}


def _body(ref: str = "r1", **over: Any) -> dict[str, Any]:
    return {"source": "webhook", "source_ref": ref, "payload": {"text": "hello"}, **over}


async def test_post_then_repeat(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    first = await client.post("/v1/items", json=_body(), headers=headers)
    again = await client.post("/v1/items", json=_body(), headers=headers)
    assert first.status_code == 202
    assert again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    jobs = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert jobs == 1


async def test_raw_is_untouched_and_hints_stored(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["admin"])
    payload = {"b": [1, 2, {"z": None}], "a": "ਪੰਜਾਬੀ"}
    body = _body(payload=payload, hints={"title": "T"}, callback_url="https://example.com/hook")
    response = await client.post("/v1/items", json=body, headers=headers)
    item = (await db_session.execute(select(Item))).scalar_one()
    assert json.dumps(item.raw, sort_keys=True) == json.dumps(payload, sort_keys=True)
    assert item.hints == {"title": "T"}
    assert item.callback_url == "https://example.com/hook"
    assert item.sensitivity == "public"
    got = await client.get(f"/v1/items/{response.json()['id']}", headers=headers)
    assert got.status_code == 200
    assert not {"raw", "hints", "callback_url"} & set(got.json())


async def test_scopes(client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant) -> None:
    read = await _key(db_session, tenant, ["items:read"])
    write = await _key(db_session, tenant, ["items:write"])
    assert (await client.post("/v1/items", json=_body(), headers=read)).status_code == 403
    assert (await client.get("/v1/items", headers=write)).status_code == 403


async def test_bulk_mixed_207(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    rows = [_body("a"), {"source": "Bad!", "source_ref": "x", "payload": 1}, _body("a"), _body("b")]
    response = await client.post("/v1/items/bulk", json={"items": rows}, headers=headers)
    assert response.status_code == 207
    results = response.json()["results"]
    assert [r["index"] for r in results] == [0, 1, 2, 3]
    assert results[1]["error"] and results[1].get("id") is None
    assert results[0]["id"] == results[2]["id"]
    assert results[3]["id"]


async def test_bulk_501_rows_is_422(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["items:write"])
    rows = [_body(f"r{i}") for i in range(501)]
    response = await client.post("/v1/items/bulk", json={"items": rows}, headers=headers)
    assert response.status_code == 422


async def test_daily_cap_429(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    settings_env: pytest.MonkeyPatch,
) -> None:
    settings_env.setenv("ITEMS_PER_DAY", "2")
    get_settings.cache_clear()
    headers = await _key(db_session, tenant, ["items:write"])
    for ref in ("a", "b"):
        assert (await client.post("/v1/items", json=_body(ref), headers=headers)).status_code == 202
    response = await client.post("/v1/items", json=_body("c"), headers=headers)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert response.json()["type"].endswith("daily-item-cap")


async def test_cursor_paging_and_filters(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _key(db_session, tenant, ["admin"])
    ids = []
    for i in range(5):
        r = await client.post("/v1/items", json=_body(f"r{i}"), headers=headers)
        ids.append(r.json()["id"])
    page1 = (await client.get("/v1/items?limit=2", headers=headers)).json()
    page2 = (
        await client.get(f"/v1/items?limit=2&cursor={page1['next_cursor']}", headers=headers)
    ).json()
    page3 = (
        await client.get(f"/v1/items?limit=2&cursor={page2['next_cursor']}", headers=headers)
    ).json()
    seen = [i["id"] for p in (page1, page2, page3) for i in p["data"]]
    assert seen == list(reversed(ids))
    assert page3["next_cursor"] is None
    other = (await client.get("/v1/items?source=gmail", headers=headers)).json()
    assert other["data"] == []
    assert (await client.get("/v1/items?limit=201", headers=headers)).status_code == 422


async def test_other_tenant_gets_404(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    mine = await _key(db_session, tenant, ["admin"])
    created = await client.post("/v1/items", json=_body(), headers=mine)
    stranger = Tenant(name="Other")
    db_session.add(stranger)
    await db_session.flush()
    theirs = await _key(db_session, stranger, ["admin"])
    response = await client.get(f"/v1/items/{created.json()['id']}", headers=theirs)
    assert response.status_code == 404
    assert (await client.get("/v1/items", headers=theirs)).json()["data"] == []
