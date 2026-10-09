"""POST /v1/items/{id}/decision (FR-33, FR-34, FR-54)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph import locks, run
from app.models import Decision, Feedback, Tenant
from tests.fakes.fake_llm import FakeLLM, fake_llm  # noqa: F401
from tests.integration.graph_support import (
    DECISION_OUT,
    bearer,
    count_rows,
    load,
    make_item,
    mini_client,  # noqa: F401
    real_niches,  # noqa: F401
)

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


async def waiting_item(
    factory: SessionFactory,
    tenant: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> str:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    item_id = await make_item(factory, tenant)
    assert (await run.run_item(item_id)).interrupted
    return str(item_id)


async def post(
    client: httpx.AsyncClient, key: str, item_id: str, body: dict[str, object]
) -> httpx.Response:
    return await client.post(f"/v1/items/{item_id}/decision", json=body, headers=bearer(key))


async def test_approve_runs_actions_and_returns_done(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    response = await post(mini_client, admin_key, item_id, {"verdict": "approve"})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "done"}
    assert await count_rows(committed_db, Decision) == 1
    assert await count_rows(committed_db, Feedback) == 1


async def test_reject_reports_rejected_and_item_ends_done(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    response = await post(mini_client, admin_key, item_id, {"verdict": "reject"})

    assert response.json() == {"status": "rejected"}
    assert (await load(committed_db, uuid.UUID(item_id))).status == "done"


async def test_snooze_returns_snoozed(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)
    until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    response = await post(
        mini_client, admin_key, item_id, {"verdict": "snooze", "snooze_until": until}
    )

    assert response.json() == {"status": "snoozed"}


async def test_double_submit_gives_one_200_and_one_409(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    first = await post(mini_client, admin_key, item_id, {"verdict": "approve"})
    second = await post(mini_client, admin_key, item_id, {"verdict": "approve"})

    assert (first.status_code, second.status_code) == (200, 409)
    assert second.headers["content-type"].startswith("application/problem+json")
    assert second.json()["type"].endswith("/not-awaiting-approval")
    assert await count_rows(committed_db, Decision) == 1


async def test_concurrent_submits_one_wins(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    responses = await asyncio.gather(
        *(post(mini_client, admin_key, item_id, {"verdict": "approve"}) for _ in range(2))
    )

    assert sorted(r.status_code for r in responses) == [200, 409]
    assert await count_rows(committed_db, Decision) == 1


async def test_busy_item_is_409_item_busy(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    async with locks.item_lock(item_id):
        response = await post(mini_client, admin_key, item_id, {"verdict": "approve"})

    assert response.status_code == 409
    assert response.json()["type"].endswith("/item-busy")


async def test_unknown_option_is_422_and_other_tenant_is_404(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    bad_option = await post(mini_client, admin_key, item_id, {"verdict": "approve", "option": "E"})
    missing = await post(
        mini_client, admin_key, "00000000-0000-7000-8000-000000000000", {"verdict": "approve"}
    )
    snooze_in_past = await post(
        mini_client,
        admin_key,
        item_id,
        {"verdict": "snooze", "snooze_until": "2020-01-01T00:00:00Z"},
    )

    assert bad_option.status_code == 422
    assert missing.status_code == 404
    assert snooze_in_past.status_code == 422
    assert (await post(mini_client, admin_key, item_id, {"verdict": "approve"})).status_code == 200


async def test_requires_items_write_scope(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    from app.core.config import get_settings
    from app.security.api_keys import create_api_key

    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with committed_db() as session:
        key = await create_api_key(session, tenant_committed.id, "r", ["items:read"], pepper)
        await session.commit()

    no_key = await mini_client.post(f"/v1/items/{item_id}/decision", json={"verdict": "approve"})
    read_only = await post(mini_client, key, item_id, {"verdict": "approve"})

    assert (no_key.status_code, read_only.status_code) == (401, 403)
