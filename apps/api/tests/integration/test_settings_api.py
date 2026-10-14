"""Tenant settings and item activity over HTTP: validation, scopes, notifier marker (FR-43)."""

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import ActionLog, Tenant, TenantSettings
from app.security.api_keys import create_api_key

pytestmark = pytest.mark.integration

SETTINGS = "/v1/settings"
VALID = {
    "quiet_hours": [23, 6],
    "digest_hour": 9,
    "ping_cap_per_day": 5,
    "interests": ["  ai ", "crypto"],
    "languages": ["en", "pa"],
}


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def read_only_key(committed_db: async_sessionmaker[AsyncSession], tenant: Tenant) -> str:
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with committed_db() as session:
        key = await create_api_key(session, tenant.id, "reader", ["items:read"], pepper)
        await session.commit()
        return key


async def test_defaults_are_returned_before_anything_is_saved(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    response = await api_client.get(SETTINGS, headers=bearer(admin_key))

    assert response.status_code == 200
    assert response.json() == {
        "quiet_hours": [22, 7],
        "digest_hour": 8,
        "ping_cap_per_day": 3,
        "interests": [],
        "languages": ["en"],
    }


async def test_put_then_get_round_trips_with_trimmed_interests(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    saved = await api_client.put(SETTINGS, json=VALID, headers=bearer(admin_key))
    read = await api_client.get(SETTINGS, headers=bearer(admin_key))

    assert saved.status_code == 200
    assert read.json() == {**VALID, "interests": ["ai", "crypto"]}


@pytest.mark.parametrize(
    "change",
    [
        {"digest_hour": 24},
        {"quiet_hours": [22, 7, 1]},
        {"languages": ["fr"]},
        {"ping_cap_per_day": 999},
        {"unknown_key": True},
    ],
)
async def test_out_of_range_or_unknown_settings_are_refused(
    api_client: httpx.AsyncClient, admin_key: str, change: dict[str, object]
) -> None:
    response = await api_client.put(SETTINGS, json={**VALID, **change}, headers=bearer(admin_key))

    assert response.status_code == 422


async def test_a_read_only_key_cannot_change_settings(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    key = await read_only_key(committed_db, tenant_committed)

    response = await api_client.put(SETTINGS, json=VALID, headers=bearer(key))
    read = await api_client.get(SETTINGS, headers=bearer(key))

    assert response.status_code == 403
    assert read.status_code == 200


async def test_saving_keeps_the_notifier_digest_marker(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    async with committed_db() as session:
        session.add(
            TenantSettings(tenant_id=tenant_committed.id, settings={"digest_sent_on": "2026-10-13"})
        )
        await session.commit()

    await api_client.put(SETTINGS, json=VALID, headers=bearer(admin_key))

    async with committed_db() as session:
        row = await session.get(TenantSettings, tenant_committed.id)
        assert row is not None and row.settings["digest_sent_on"] == "2026-10-13"


async def test_put_waits_for_a_row_lock_and_keeps_a_concurrent_marker_write(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    async with committed_db() as session:
        session.add(TenantSettings(tenant_id=tenant_committed.id, settings={"digest_hour": 1}))
        await session.commit()

    async with committed_db() as notifier:
        locked = await notifier.scalar(
            select(TenantSettings)
            .where(TenantSettings.tenant_id == tenant_committed.id)
            .with_for_update()
        )
        assert locked is not None
        put = asyncio.create_task(api_client.put(SETTINGS, json=VALID, headers=bearer(admin_key)))
        await asyncio.sleep(0.5)
        assert not put.done()  # the PUT is blocked on the notifier's row lock
        locked.settings = {**locked.settings, "digest_sent_on": "2026-10-14"}
        await notifier.commit()

    response = await asyncio.wait_for(put, timeout=10)

    assert response.status_code == 200
    async with committed_db() as session:
        row = await session.get(TenantSettings, tenant_committed.id)
        assert row is not None
        assert row.settings["digest_sent_on"] == "2026-10-14"
        assert row.settings["digest_hour"] == VALID["digest_hour"]


async def test_concurrent_first_puts_both_succeed(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    other = {**VALID, "digest_hour": 11}

    first, second = await asyncio.gather(
        api_client.put(SETTINGS, json=VALID, headers=bearer(admin_key)),
        api_client.put(SETTINGS, json=other, headers=bearer(admin_key)),
    )

    assert first.status_code == 200 and second.status_code == 200
    async with committed_db() as session:
        row = await session.get(TenantSettings, tenant_committed.id)
        assert row is not None and row.settings["digest_hour"] in (9, 11)


async def test_activity_lists_only_this_items_actions(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    mine = await api_client.post(
        "/v1/items",
        json={"source": "manual", "source_ref": "act-1", "payload": {"text": "hello"}},
        headers=bearer(admin_key),
    )
    other = await api_client.post(
        "/v1/items",
        json={"source": "manual", "source_ref": "act-2", "payload": {"text": "other"}},
        headers=bearer(admin_key),
    )
    item_id = uuid.UUID(mine.json()["id"])
    async with committed_db() as session:
        session.add(
            ActionLog(
                tenant_id=tenant_committed.id,
                item_id=item_id,
                action="archive",
                idem_key=f"{item_id}:archive",
                status="done",
                params={"url": "https://example.com/secret-link"},
            )
        )
        await session.commit()

    activity = await api_client.get(f"/v1/items/{item_id}/activity", headers=bearer(admin_key))
    empty = await api_client.get(
        f"/v1/items/{other.json()['id']}/activity", headers=bearer(admin_key)
    )
    missing = await api_client.get(f"/v1/items/{uuid.uuid4()}/activity", headers=bearer(admin_key))

    entries = activity.json()["data"]
    assert [entry["action"] for entry in entries] == ["archive"]
    assert "params" not in entries[0] and "result" not in entries[0]
    assert empty.json() == {"data": []}
    assert missing.status_code == 404


async def test_another_tenant_gets_404_for_activity_and_its_own_settings(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
) -> None:
    created = await api_client.post(
        "/v1/items",
        json={"source": "manual", "source_ref": "act-x", "payload": {"text": "mine"}},
        headers=bearer(admin_key),
    )
    await api_client.put(SETTINGS, json=VALID, headers=bearer(admin_key))
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with committed_db() as session:
        other = Tenant(name="Other Tenant")
        session.add(other)
        await session.commit()
        other_key = await create_api_key(session, other.id, "other", ["admin"], pepper)
        await session.commit()

    activity = await api_client.get(
        f"/v1/items/{created.json()['id']}/activity", headers=bearer(other_key)
    )
    settings = await api_client.get(SETTINGS, headers=bearer(other_key))

    assert activity.status_code == 404
    assert settings.json()["digest_hour"] != VALID["digest_hour"]
