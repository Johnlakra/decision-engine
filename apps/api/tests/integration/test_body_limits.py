"""Request/payload size limits and the hard daily cap (NFR-05, FR-02, FR-07)."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.decide import MAX_STATE_CHARS
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import get_settings
from app.models import Tenant
from app.schemas.ingest import MAX_PAYLOAD_BYTES
from tests.integration.test_items_api import _app, _body, _key

pytestmark = pytest.mark.integration
SMALL_LIMIT = 2_000


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = _app(db_session)
    app.add_middleware(BodyLimitMiddleware)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.fixture
def small_limits(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("MAX_REQUEST_BYTES", str(SMALL_LIMIT))
    settings_env.setenv("MAX_BULK_REQUEST_BYTES", str(SMALL_LIMIT * 4))
    get_settings.cache_clear()


@pytest.mark.usefixtures("small_limits")
async def test_oversized_content_length_is_413_problem_json(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: a declared body over the limit is refused with problem+json."""
    headers = await _key(db_session, tenant, ["items:write"])
    big = _body("big", payload={"t": "x" * SMALL_LIMIT})

    response = await client.post("/v1/items", json=big, headers=headers)

    assert response.status_code == 413
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 413


@pytest.mark.usefixtures("small_limits")
async def test_streamed_body_without_content_length_is_413(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: limit is enforced by counting when Content-Length is absent."""
    headers = await _key(db_session, tenant, ["items:write"])
    raw = json.dumps(_body("big", payload={"t": "x" * SMALL_LIMIT})).encode()

    async def chunks() -> AsyncIterator[bytes]:
        for i in range(0, len(raw), 500):
            yield raw[i : i + 500]

    response = await client.post(
        "/v1/items", content=chunks(), headers={**headers, "Content-Type": "application/json"}
    )

    assert response.status_code == 413
    assert "content-length" not in response.request.headers


@pytest.mark.usefixtures("small_limits")
async def test_body_just_under_limit_is_accepted(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: a request just under the limit still ingests."""
    headers = await _key(db_session, tenant, ["items:write"])
    overhead = len(json.dumps(_body("ok", payload={"t": ""})))
    body = _body("ok", payload={"t": "x" * (SMALL_LIMIT - overhead - 10)})
    assert len(json.dumps(body)) < SMALL_LIMIT

    response = await client.post("/v1/items", json=body, headers=headers)

    assert response.status_code == 202


@pytest.mark.usefixtures("small_limits")
async def test_bulk_uses_the_larger_limit(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: bulk has its own, larger cap."""
    headers = await _key(db_session, tenant, ["items:write"])
    rows = [_body(f"b{i}", payload={"t": "x" * 500}) for i in range(5)]  # ~3 KB > single limit

    response = await client.post("/v1/items/bulk", json={"items": rows}, headers=headers)

    assert response.status_code == 207


async def test_payload_over_serialized_cap_is_422(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: payload serialized size is capped independent of the body limit."""
    headers = await _key(db_session, tenant, ["items:write"])
    big = _body("big", payload={"t": "x" * MAX_PAYLOAD_BYTES})

    response = await client.post("/v1/items", json=big, headers=headers)

    assert response.status_code == 422


async def test_payload_just_under_serialized_cap_is_accepted(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    """NFR-05: a payload just under the cap is stored."""
    headers = await _key(db_session, tenant, ["items:write"])
    filler = MAX_PAYLOAD_BYTES - len('{"t": ""}') - 1
    body = _body("ok", payload={"t": "x" * filler})

    response = await client.post("/v1/items", json=body, headers=headers)

    assert response.status_code == 202


async def test_decide_dict_state_over_cap_is_rejected() -> None:
    """NFR-05: structured decide state is capped before json.dumps/as_data."""
    from pydantic import ValidationError

    from app.api.v1.decide import DecideIn

    with pytest.raises(ValidationError):
        DecideIn(state={"t": "x" * MAX_STATE_CHARS})
    with pytest.raises(ValidationError):
        DecideIn(state=["x" * MAX_STATE_CHARS])
    assert DecideIn(state={"t": "x" * 100}).state == {"t": "x" * 100}
