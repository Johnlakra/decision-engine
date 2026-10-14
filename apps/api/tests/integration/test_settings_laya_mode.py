"""Laya mode through /v1/settings: off/shadow editable, 'on' gated (FR-23, FR-24; ADR 0008)."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import Tenant, TenantSettings

pytestmark = pytest.mark.integration

SETTINGS = "/v1/settings"
FIVE = {
    "quiet_hours": [22, 7],
    "digest_hour": 8,
    "ping_cap_per_day": 3,
    "interests": ["ai"],
    "languages": ["en"],
}


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def _put(client: httpx.AsyncClient, key: str, **extra: object) -> httpx.Response:
    return await client.put(SETTINGS, json={**FIVE, **extra}, headers=bearer(key))


async def _stored(
    committed_db: async_sessionmaker[AsyncSession], tenant: Tenant
) -> dict[str, object]:
    async with committed_db() as session:
        row = await session.scalar(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant.id)
        )
        return dict(row.settings) if row else {}


async def _seed(
    committed_db: async_sessionmaker[AsyncSession], tenant: Tenant, stored: dict[str, object]
) -> None:
    async with committed_db() as session:
        session.add(TenantSettings(tenant_id=tenant.id, settings=stored))
        await session.commit()


async def test_five_field_body_still_works_and_leaves_laya_keys_alone(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    await _seed(
        committed_db, tenant_committed, {"laya_mode": "off", "laya_mode_by_niche": {"inbox": "off"}}
    )

    resp = await _put(api_client, admin_key)

    assert resp.status_code == 200
    assert resp.json()["laya_mode"] == "off"
    assert resp.json()["laya_mode_by_niche"] == {"inbox": "off"}
    stored = await _stored(committed_db, tenant_committed)
    assert stored["laya_mode"] == "off" and stored["laya_mode_by_niche"] == {"inbox": "off"}


async def test_set_both_fields_and_read_back_with_default(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    resp = await _put(
        api_client, admin_key, laya_mode="shadow", laya_mode_by_niche={"news_radar": "off"}
    )

    assert resp.status_code == 200
    expected = {
        "laya_mode": "shadow",
        "laya_mode_by_niche": {"news_radar": "off"},
        "laya_mode_default": get_settings().laya_mode,
    }
    assert {k: resp.json()[k] for k in expected} == expected
    read = await api_client.get(SETTINGS, headers=bearer(admin_key))
    assert {k: read.json()[k] for k in expected} == expected


async def test_null_clears_the_tenant_mode_and_is_never_stored_as_json_null(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    await _put(api_client, admin_key, laya_mode="off")

    resp = await _put(api_client, admin_key, laya_mode=None)

    assert resp.json()["laya_mode"] is None
    assert "laya_mode" not in await _stored(committed_db, tenant_committed)


async def test_absent_keeps_and_empty_map_clears_overrides(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    await _put(api_client, admin_key, laya_mode="off", laya_mode_by_niche={"inbox": "shadow"})

    kept = await _put(api_client, admin_key, laya_mode_by_niche={"inbox": "shadow"})
    assert kept.json()["laya_mode"] == "off"  # laya_mode absent: unchanged

    cleared = await _put(api_client, admin_key, laya_mode_by_niche={})
    assert cleared.json()["laya_mode_by_niche"] == {}
    assert cleared.json()["laya_mode"] == "off"


async def test_map_is_a_full_replacement(api_client: httpx.AsyncClient, admin_key: str) -> None:
    await _put(api_client, admin_key, laya_mode_by_niche={"inbox": "off", "news_radar": "off"})

    resp = await _put(api_client, admin_key, laya_mode_by_niche={"generic": "shadow"})

    assert resp.json()["laya_mode_by_niche"] == {"generic": "shadow"}


async def test_change_to_on_is_gated_with_a_problem(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    await _put(api_client, admin_key, laya_mode="shadow")

    resp = await _put(api_client, admin_key, laya_mode="on")

    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["type"] == "https://decision-engine/problems/laya-mode-gated"
    assert body["title"] == "Laya 'on' needs the calibration gate"
    assert body["errors"] == [
        {
            "field": "body.laya_mode",
            "message": "'on' is not available from the API yet",
            "code": "laya_mode_gated",
        }
    ]
    read = await api_client.get(SETTINGS, headers=bearer(admin_key))
    assert read.json()["laya_mode"] == "shadow"


async def test_gate_applies_per_niche_and_to_unset_values(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    resp = await _put(api_client, admin_key, laya_mode_by_niche={"inbox": "on"})

    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "body.laya_mode_by_niche.inbox"
    assert resp.json()["errors"][0]["code"] == "laya_mode_gated"
    assert (await _put(api_client, admin_key, laya_mode="on")).status_code == 422


async def test_resending_a_stored_on_is_accepted_and_on_can_go_back_down(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    await _seed(
        committed_db, tenant_committed, {"laya_mode": "on", "laya_mode_by_niche": {"inbox": "on"}}
    )

    same = await _put(api_client, admin_key, laya_mode="on", laya_mode_by_niche={"inbox": "on"})
    assert same.status_code == 200 and same.json()["laya_mode"] == "on"

    down = await _put(
        api_client, admin_key, laya_mode="off", laya_mode_by_niche={"inbox": "shadow"}
    )
    assert down.status_code == 200
    assert down.json()["laya_mode"] == "off"
    assert (await _put(api_client, admin_key, laya_mode="on")).status_code == 422  # no way back up


@pytest.mark.parametrize("name", ["nope", "Inbox", "../etc", "x" * 41, ""])
async def test_unknown_niche_is_422(
    api_client: httpx.AsyncClient, admin_key: str, name: str
) -> None:
    resp = await _put(api_client, admin_key, laya_mode_by_niche={name: "off"})

    assert resp.status_code == 422
    error = resp.json()["errors"][0]
    assert error["code"] == "unknown_niche" and error["field"].startswith("body.laya_mode_by_niche")


async def test_disabled_niches_are_still_known(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    resp = await _put(api_client, admin_key, laya_mode_by_niche={"agriculture": "off"})

    assert resp.status_code == 200


@pytest.mark.parametrize(
    "extra",
    [
        {"laya_mode": "sometimes"},
        {"laya_mode": 1},
        {"laya_mode_by_niche": {"inbox": "maybe"}},
        {"laya_mode_by_niche": None},
        {"laya_mode_by_niche": ["inbox"]},
        {"laya_mode_default": "off"},
    ],
)
async def test_bad_shapes_are_422(
    api_client: httpx.AsyncClient, admin_key: str, extra: dict[str, object]
) -> None:
    assert (await _put(api_client, admin_key, **extra)).status_code == 422


async def test_more_than_fifty_entries_is_422(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    too_many = {f"niche_{i:02d}": "off" for i in range(51)}

    assert (await _put(api_client, admin_key, laya_mode_by_niche=too_many)).status_code == 422


async def test_invalid_stored_values_read_as_null_and_are_dropped(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    await _seed(
        committed_db,
        tenant_committed,
        {"laya_mode": "bogus", "laya_mode_by_niche": {"inbox": "off", "generic": 5}},
    )

    body = (await api_client.get(SETTINGS, headers=bearer(admin_key))).json()

    assert body["laya_mode"] is None and body["laya_mode_by_niche"] == {"inbox": "off"}


async def test_default_mirrors_env(
    api_client: httpx.AsyncClient, admin_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LAYA_MODE", "off")
    get_settings.cache_clear()
    try:
        body = (await api_client.get(SETTINGS, headers=bearer(admin_key))).json()
    finally:
        get_settings.cache_clear()

    assert body["laya_mode_default"] == "off"


async def test_read_only_key_cannot_write_laya_mode(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    tenant_committed: Tenant,
) -> None:
    from tests.integration.test_settings_api import read_only_key

    key = await read_only_key(committed_db, tenant_committed)

    assert (await _put(api_client, key, laya_mode="off")).status_code == 403
