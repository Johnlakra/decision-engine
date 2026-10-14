"""GET /v1/niches, GET /v1/niches/{name}, PUT /v1/niches/{name}, reload (FR-70, ADR 0009, 0011)."""

import copy
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import registered as registered_actions
from app.api.deps import get_rate_limiter
from app.core.config import REPO_ROOT, get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import Niche, Tenant, TenantSettings
from app.niches import overrides
from app.niches import registry as registry_mod
from app.niches.registry import NicheRegistry
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter
from app.tools.registry import registered as registered_tools

pytestmark = pytest.mark.integration

STARTERS = ["agriculture", "generic", "inbox", "news_radar", "tech_stack"]


@pytest.fixture
def niches_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "niches"
    shutil.copytree(REPO_ROOT / "niches", target)
    monkeypatch.setenv("NICHES_DIR", str(target))
    get_settings.cache_clear()
    monkeypatch.setattr(registry_mod, "_registry", None)
    return target


@pytest_asyncio.fixture
async def client(niches_dir: Path, db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        yield http
    get_settings.cache_clear()


async def _headers(session: AsyncSession, tenant: Tenant, scopes: list[str]) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    key = await create_api_key(session, tenant.id, "t", scopes, pepper)
    return {"Authorization": f"Bearer {key}"}


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession, tenant: Tenant) -> dict[str, str]:
    return await _headers(db_session, tenant, ["admin"])


async def _effective(
    client: httpx.AsyncClient, admin: dict[str, str], name: str, *, only_registered: bool = True
) -> dict[str, Any]:
    """Effective config. Shipped niches name actions/tools that are not built yet (inbox:
    draft_reply, news_radar: notify, agriculture: Phase 7 tools); ADR 0009 refuses those on PUT,
    so tests drop them unless they test exactly that."""
    resp = await client.get(f"/v1/niches/{name}", headers=admin)
    assert resp.status_code == 200, resp.text
    config: dict[str, Any] = copy.deepcopy(resp.json()["config"])
    if only_registered:
        config["actions"] = [a for a in config["actions"] if a in registered_actions()]
        config["tools"] = [t for t in config.get("tools", []) if t in registered_tools()]
        config["auto_actions"] = [
            a for a in config.get("auto_actions", []) if a in config["actions"]
        ]
    return config


async def _put(
    client: httpx.AsyncClient, admin: dict[str, str], name: str, body: Any
) -> httpx.Response:
    return await client.put(f"/v1/niches/{name}", headers=admin, json=body)


async def _rows(db_session: AsyncSession) -> int:
    return int(await db_session.scalar(select(func.count(Niche.id))) or 0)


# ---- reads ----------------------------------------------------------------------------------


async def test_list_requires_key_and_reader_scope(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    assert (await client.get("/v1/niches")).status_code == 401
    only_write = await _headers(db_session, tenant, ["items:write"])
    assert (await client.get("/v1/niches", headers=only_write)).status_code == 403


async def test_list_rows(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _headers(db_session, tenant, ["items:read"])
    resp = await client.get("/v1/niches", headers=headers)
    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert [r["name"] for r in rows] == STARTERS
    inbox = next(r for r in rows if r["name"] == "inbox")
    assert set(inbox) == {
        "name", "label", "description", "enabled", "autonomy", "auto_actions",
        "source", "version", "laya_mode",
    }  # fmt: skip
    assert inbox["source"] == "yaml" and inbox["laya_mode"] == "shadow"
    assert next(r for r in rows if r["name"] == "agriculture")["enabled"] is False


async def test_list_laya_mode_is_effective(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    db_session.add(
        TenantSettings(
            tenant_id=tenant.id,
            settings={"laya_mode": "off", "laya_mode_by_niche": {"inbox": "shadow"}},
        )
    )
    await db_session.flush()
    headers = await _headers(db_session, tenant, ["items:read"])
    rows = {r["name"]: r for r in (await client.get("/v1/niches", headers=headers)).json()["data"]}
    assert rows["inbox"]["laya_mode"] == "shadow"
    assert rows["generic"]["laya_mode"] == "off"


async def test_get_one_has_config_and_yaml_text(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    body = (await client.get("/v1/niches/inbox", headers=admin)).json()
    assert body["name"] == "inbox" and body["source"] == "yaml" and body["version"] == 1
    assert body["config"]["name"] == "inbox"
    assert body["yaml"] == (REPO_ROOT / "niches" / "inbox.yaml").read_text(encoding="utf-8")
    assert None not in body["config"].values()  # nulls dropped so the config can be echoed to PUT


async def test_get_unknown_is_404_problem(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    resp = await client.get("/v1/niches/nope", headers=admin)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


# ---- PUT: happy path ------------------------------------------------------------------------


@pytest.mark.parametrize("name", STARTERS)
async def test_effective_config_round_trips_through_put(
    client: httpx.AsyncClient, admin: dict[str, str], name: str
) -> None:
    config = await _effective(client, admin, name)
    resp = await _put(client, admin, name, config)
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"] == {**config, "version": 1}


@pytest.mark.parametrize(
    ("name", "field", "value"),
    [
        ("inbox", "autonomy", "ask"),
        ("news_radar", "autonomy", "ask"),
        ("agriculture", "description", "edited through the API"),
    ],
)
async def test_shipped_niche_with_unbuilt_entries_round_trips_when_unchanged(
    client: httpx.AsyncClient, admin: dict[str, str], name: str, field: str, value: str
) -> None:
    # ADR 0009 amendment: registry checks apply to changed entries only
    config = await _effective(client, admin, name, only_registered=False)
    config[field] = value
    config["actions"] = list(reversed(config["actions"]))  # order is ignored
    resp = await _put(client, admin, name, config)
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"][field] == value


async def test_adding_unregistered_action_or_tool_is_refused_at_its_index(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "agriculture", only_registered=False)
    config["actions"] = [*config["actions"], "launch_missiles"]
    config["tools"] = [*config["tools"], "nope.tool"]
    errors = await _expect_422(client, admin, db_session, "agriculture", config)
    assert [e["json_pointer"] for e in errors] == [
        f"/actions/{len(config['actions']) - 1}",
        f"/tools/{len(config['tools']) - 1}",
    ]


async def test_db_only_niche_checks_every_entry(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "news_radar")
    config.update(name="job_offers", label="Job offers", auto_actions=[], autonomy="ask")
    config["actions"] = [*config["actions"], "draft_reply"]
    errors = await _expect_422(client, admin, db_session, "job_offers", config)
    assert [e["json_pointer"] for e in errors] == [f"/actions/{len(config['actions']) - 1}"]


async def test_auto_action_added_or_orphaned_by_this_put_is_refused(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    added = await _effective(client, admin, "news_radar")
    added["auto_actions"] = [*added["auto_actions"], "ghost"]
    errors = await _expect_422(client, admin, db_session, "news_radar", added)
    assert [e["json_pointer"] for e in errors] == [
        f"/auto_actions/{len(added['auto_actions']) - 1}"
    ]
    orphaned = await _effective(client, admin, "news_radar")
    assert orphaned["auto_actions"] == ["archive"]
    orphaned["actions"] = [a for a in orphaned["actions"] if a != "archive"]
    errors = await _expect_422(client, admin, db_session, "news_radar", orphaned)
    assert [e["json_pointer"] for e in errors] == ["/auto_actions/0"]


async def test_baseline_is_the_stored_override_when_one_exists(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    shipped = await _effective(client, admin, "inbox", only_registered=False)
    assert "draft_reply" in shipped["actions"]
    kept = await _put(client, admin, "inbox", shipped)  # in the YAML baseline: allowed
    assert kept.status_code == 200, kept.text
    removed = {**shipped, "actions": [a for a in shipped["actions"] if a != "draft_reply"]}
    assert (await _put(client, admin, "inbox", removed)).status_code == 200
    # the override no longer has it, so putting it back counts as adding it
    errors = await _expect_422(client, admin, db_session, "inbox", shipped)
    assert [e["json_pointer"] for e in errors] == [
        f"/actions/{shipped['actions'].index('draft_reply')}"
    ]


async def test_put_requires_admin(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "inbox")
    reader = await _headers(db_session, tenant, ["items:read", "items:write"])
    assert (await _put(client, reader, "inbox", config)).status_code == 403
    assert (await client.put("/v1/niches/inbox", json=config)).status_code == 401


async def test_put_stores_override_bumps_version_and_ignores_body_version(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["description"] = "a message that needs a reply, edited through the API"
    first = await _put(client, admin, "inbox", {**config, "version": 99})
    assert first.status_code == 200
    body = first.json()
    assert body["source"] == "db" and body["version"] == 1
    assert body["config"]["description"] == config["description"]
    assert body["config"]["version"] == 1
    second = await _put(client, admin, "inbox", config)
    assert second.json()["version"] == 2 and second.json()["config"]["version"] == 2
    row = await db_session.scalar(select(Niche).where(Niche.name == "inbox"))
    assert row is not None
    assert row.version == 2 and row.source == "db" and row.enabled == config["enabled"]
    assert row.config["version"] == 2
    listed = (await client.get("/v1/niches", headers=admin)).json()["data"]
    inbox = next(r for r in listed if r["name"] == "inbox")
    assert inbox["source"] == "db" and inbox["version"] == 2
    assert "yaml" in (await client.get("/v1/niches/inbox", headers=admin)).json()


async def test_put_dumps_yaml_for_db_override(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "news_radar")
    await _put(client, admin, "news_radar", config)
    body = (await client.get("/v1/niches/news_radar", headers=admin)).json()
    assert body["source"] == "db" and body["yaml"].startswith("name: news_radar")


async def test_put_can_create_db_only_niche(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "news_radar")
    config.update(name="job_offers", label="Job offers")
    resp = await _put(client, admin, "job_offers", config)
    assert resp.status_code == 200 and resp.json()["source"] == "db"
    names = [r["name"] for r in (await client.get("/v1/niches", headers=admin)).json()["data"]]
    assert "job_offers" in names


# ---- PUT: 422 rules -------------------------------------------------------------------------


async def _expect_422(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    db_session: AsyncSession,
    name: str,
    body: Any,
) -> list[dict[str, str]]:
    before = await _rows(db_session)
    resp = await _put(client, admin, name, body)
    assert resp.status_code == 422, resp.text
    assert resp.headers["content-type"].startswith("application/problem+json")
    problem = resp.json()
    assert problem["title"] == "Niche validation failed"
    assert await _rows(db_session) == before  # nothing written
    errors: list[dict[str, str]] = problem["errors"]
    assert all(set(e) == {"json_pointer", "message"} for e in errors)
    return errors


async def test_schema_error_has_pointer(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["autonomy"] = "yolo"
    errors = await _expect_422(client, admin, db_session, "inbox", config)
    assert [e["json_pointer"] for e in errors] == ["/autonomy"]


async def test_schema_errors_sorted_and_capped_at_20(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["tools"] = [1] * 25
    config["autonomy"] = "yolo"
    errors = await _expect_422(client, admin, db_session, "inbox", config)
    pointers = [e["json_pointer"] for e in errors]
    assert len(errors) == 20 and pointers == sorted(pointers)


async def test_semantic_checks_skipped_when_schema_fails(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config.update(autonomy="yolo", name="other")
    errors = await _expect_422(client, admin, db_session, "inbox", config)
    assert [e["json_pointer"] for e in errors] == ["/autonomy"]


@pytest.mark.parametrize("body", [[1, 2], "text", 5, None])
async def test_non_object_body_is_one_root_error(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession, body: Any
) -> None:
    errors = await _expect_422(client, admin, db_session, "inbox", body)
    assert [e["json_pointer"] for e in errors] == [""]


async def test_name_must_equal_path(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    errors = await _expect_422(client, admin, db_session, "news_radar", config)
    assert [e["json_pointer"] for e in errors] == ["/name"]


async def test_generic_cannot_be_disabled(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "generic")
    config["enabled"] = False
    errors = await _expect_422(client, admin, db_session, "generic", config)
    assert [e["json_pointer"] for e in errors] == ["/enabled"]


async def test_other_niche_can_be_disabled(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "news_radar")
    config["enabled"] = False
    resp = await _put(client, admin, "news_radar", config)
    assert resp.status_code == 200
    listed = (await client.get("/v1/niches", headers=admin)).json()["data"]
    assert next(r for r in listed if r["name"] == "news_radar")["enabled"] is False


async def test_steps_must_be_empty(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["steps"] = ["extract"]
    errors = await _expect_422(client, admin, db_session, "inbox", config)
    assert [e["json_pointer"] for e in errors] == ["/steps"]
    config["steps"] = []
    assert (await _put(client, admin, "inbox", config)).status_code == 200


async def test_unregistered_action_and_tool(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "tech_stack")
    config["actions"] = [*config["actions"], "launch_missiles"]
    config["tools"] = ["nope.tool", *config["tools"]]
    errors = await _expect_422(client, admin, db_session, "tech_stack", config)
    pointers = [e["json_pointer"] for e in errors]
    assert f"/actions/{len(config['actions']) - 1}" in pointers and "/tools/0" in pointers


async def test_auto_actions_must_be_in_actions(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "tech_stack")
    config["autonomy"] = "auto"
    config["auto_actions"] = ["webhook", "create_task"]
    config["actions"] = ["webhook"]
    errors = await _expect_422(client, admin, db_session, "tech_stack", config)
    assert [e["json_pointer"] for e in errors] == ["/auto_actions/1"]


async def test_safety_floor_expert_review_and_ask(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    db_session: AsyncSession,
    niches_dir: Path,
) -> None:
    # No shipped niche has expert_review.always today, so add one to the YAML directory.
    shipped = (REPO_ROOT / "niches" / "tech_stack.yaml").read_text(encoding="utf-8")
    guarded = shipped.replace("name: tech_stack", "name: guarded")
    guarded += "expert_review: {always: true}\n"
    (niches_dir / "guarded.yaml").write_text(guarded.replace("autonomy: suggest", "autonomy: ask"))
    assert (await client.post("/v1/niches/reload", headers=admin)).status_code == 200
    config = await _effective(client, admin, "guarded")
    assert config["expert_review"]["always"] is True and config["autonomy"] == "ask"
    weak = copy.deepcopy(config)
    weak["expert_review"]["always"] = False
    weak["autonomy"] = "auto"
    weak["auto_actions"] = [weak["actions"][0]]
    errors = await _expect_422(client, admin, db_session, "guarded", weak)
    assert {e["json_pointer"] for e in errors} == {"/expert_review/always", "/autonomy"}
    suggest = {**config, "autonomy": "suggest"}
    errors = await _expect_422(client, admin, db_session, "guarded", suggest)
    assert [e["json_pointer"] for e in errors] == ["/autonomy"]
    assert (await _put(client, admin, "guarded", config)).status_code == 200


async def test_safety_floor_agriculture_refuses_auto_autonomy(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "agriculture")
    config["autonomy"] = "auto"
    config["auto_actions"] = [config["actions"][0]] if config["actions"] else []
    errors = await _expect_422(client, admin, db_session, "agriculture", config)
    assert "/autonomy" in [e["json_pointer"] for e in errors]


async def test_safety_floor_agriculture_ask_with_topics_succeeds(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "agriculture")
    assert config["autonomy"] == "ask" and config["expert_review"]["when_topics"]
    resp = await _put(client, admin, "agriculture", config)
    assert resp.status_code == 200, resp.text


async def test_safety_floor_agriculture_refuses_removing_topics(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "agriculture")
    config["expert_review"] = {"always": False, "when_topics": []}
    errors = await _expect_422(client, admin, db_session, "agriculture", config)
    assert [e["json_pointer"] for e in errors] == ["/expert_review"]
    config["expert_review"] = {"always": False}
    errors = await _expect_422(client, admin, db_session, "agriculture", config)
    assert [e["json_pointer"] for e in errors] == ["/expert_review"]


async def test_safety_floor_private_stays_private(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["sensitivity"] = "public"
    errors = await _expect_422(client, admin, db_session, "inbox", config)
    assert [e["json_pointer"] for e in errors] == ["/sensitivity"]


async def test_public_yaml_niche_may_become_private(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "news_radar")
    config["sensitivity"] = "private"
    assert (await _put(client, admin, "news_radar", config)).status_code == 200


# ---- sync and reload ------------------------------------------------------------------------


async def test_second_registry_sees_put_after_sync(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    db_session: AsyncSession,
    niches_dir: Path,
) -> None:
    other = NicheRegistry(niches_dir, get_settings().schemas_dir)
    other.reload()
    config = await _effective(client, admin, "inbox")
    config["description"] = "second process should see this edited description"
    assert (await _put(client, admin, "inbox", config)).status_code == 200
    stale = other.get("inbox")
    assert stale is not None and stale.description != config["description"]
    assert await overrides.sync_registry(db_session, other) is True
    fresh = other.get("inbox")
    assert fresh is not None and fresh.description == config["description"]
    assert await overrides.sync_registry(db_session, other) is False


async def test_reload_reapplies_db_overrides(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    config = await _effective(client, admin, "inbox")
    config["description"] = "kept across a YAML reload of the files"
    await _put(client, admin, "inbox", config)
    resp = await client.post("/v1/niches/reload", headers=admin)
    assert resp.status_code == 200
    inbox = registry_mod.get_registry().get("inbox")
    assert inbox is not None and inbox.description == config["description"]
    assert registry_mod.get_registry().source("inbox") == "db"


async def test_reload_after_row_delete_falls_back_to_yaml(
    client: httpx.AsyncClient, admin: dict[str, str], db_session: AsyncSession
) -> None:
    config = await _effective(client, admin, "inbox")
    config["description"] = "temporary override that will be deleted"
    await _put(client, admin, "inbox", config)
    row = await db_session.scalar(select(Niche).where(Niche.name == "inbox"))
    assert row is not None
    await db_session.delete(row)
    await db_session.flush()
    listed = (await client.get("/v1/niches", headers=admin)).json()["data"]  # sync on read
    assert next(r for r in listed if r["name"] == "inbox")["source"] == "yaml"


async def test_decide_and_decision_routes_sync_the_registry(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import uuid

    from app.api.v1 import decide as decide_mod
    from app.api.v1 import decisions as decisions_mod

    calls: list[str] = []

    async def fake_sync(_session: AsyncSession, registry: object = None) -> bool:
        calls.append("sync")
        raise RuntimeError("stop after the sync call")

    monkeypatch.setattr(decide_mod, "sync_registry", fake_sync)
    monkeypatch.setattr(decisions_mod, "sync_registry", fake_sync)
    headers = await _headers(db_session, tenant, ["admin"])
    with pytest.raises(RuntimeError, match="stop after"):
        await client.post(
            f"/v1/items/{uuid.uuid4()}/decision", headers=headers, json={"verdict": "reject"}
        )
    assert calls == ["sync"]
    with pytest.raises(RuntimeError, match="stop after"):
        await client.post("/v1/decide", headers=headers, json={"state": "hi", "questions": {}})
    assert calls == ["sync", "sync"]
