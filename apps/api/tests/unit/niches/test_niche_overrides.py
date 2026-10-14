"""DB niche overrides: merge into the registry, fingerprint sync (FR-70, FR-71, ADR 0009)."""

import copy
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.exc import OperationalError

from app.core.config import REPO_ROOT
from app.niches import overrides
from app.niches.loader import load_niche_file
from app.niches.registry import NicheRegistry

SCHEMAS = REPO_ROOT / "schemas"


@pytest.fixture
def niches_dir(tmp_path: Path) -> Path:
    target = tmp_path / "niches"
    shutil.copytree(REPO_ROOT / "niches", target)
    return target


def _config(base: str, **changes: Any) -> dict[str, Any]:
    cfg = load_niche_file(REPO_ROOT / "niches" / f"{base}.yaml", SCHEMAS).model_dump(
        mode="json", exclude_none=True
    )
    return {**copy.deepcopy(cfg), **changes}


def test_override_replaces_yaml_niche_and_marks_source_db(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    result = registry.reload(
        overrides={"inbox": _config("inbox", description="from db override description", version=4)}
    )
    assert result.errors == []
    inbox = registry.get("inbox")
    assert (
        inbox is not None
        and inbox.description == "from db override description"
        and inbox.version == 4
    )
    assert registry.source("inbox") == "db"
    assert registry.source("generic") == "yaml"
    assert registry.yaml_config("inbox") is not None
    assert registry.yaml_config("inbox").description != "from db override description"  # type: ignore[union-attr]


def test_invalid_override_keeps_yaml_and_reports_error(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    yaml_inbox = None
    result = registry.reload(overrides={"inbox": _config("inbox", autonomy="yolo")})
    yaml_inbox = registry.get("inbox")
    assert yaml_inbox is not None and yaml_inbox.autonomy != "yolo"
    assert registry.source("inbox") == "yaml"
    assert [(e.file, e.json_pointer) for e in result.errors] == [("db:inbox", "/autonomy")]
    assert registry.errors == result.errors


def test_override_name_must_match_row_name(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    result = registry.reload(overrides={"inbox": _config("news_radar")})
    assert [e.json_pointer for e in result.errors] == ["/name"]
    assert registry.source("inbox") == "yaml"


def test_db_only_niche_is_loaded(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    cfg = _config("inbox", name="job_offers", label="Jobs")
    registry.reload(overrides={"job_offers": cfg})
    assert registry.source("job_offers") == "db"
    assert registry.yaml_config("job_offers") is None


def test_removed_override_falls_back_to_yaml(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload(
        overrides={"inbox": _config("inbox", description="from db override description")}
    )
    registry.reload(overrides={})
    inbox = registry.get("inbox")
    assert inbox is not None and inbox.description != "from db override description"
    assert registry.source("inbox") == "yaml"


class _Rows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def one(self) -> Any:
        return self._rows[0]


class _FakeSession:
    def __init__(self, rows: list[Any], fingerprint: Any = (0, 0, None)) -> None:
        self.rows = rows
        self.fingerprint = fingerprint
        self.calls = 0

    async def execute(self, stmt: Any) -> _Rows:
        self.calls += 1
        if "count" in str(stmt).lower():
            if isinstance(self.fingerprint, Exception):
                raise self.fingerprint
            return _Rows([self.fingerprint])
        return _Rows(self.rows)

    def begin_nested(self) -> Any:
        return _Nested()


class _Nested:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


async def test_load_overrides_applies_none_for_multiple_tenants(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = [
        (uuid.uuid4(), "inbox", _config("inbox")),
        (uuid.uuid4(), "news_radar", _config("news_radar")),
    ]
    with caplog.at_level("ERROR"):
        loaded = await overrides.load_overrides(_FakeSession(rows))  # type: ignore[arg-type]
    assert loaded == {}
    assert "more than one tenant" in caplog.text


async def test_load_overrides_single_tenant_maps_by_name() -> None:
    tid = uuid.uuid4()
    rows = [(tid, "inbox", _config("inbox"))]
    loaded = await overrides.load_overrides(_FakeSession(rows))  # type: ignore[arg-type]
    assert list(loaded) == ["inbox"]


async def test_sync_reloads_once_per_fingerprint_change(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    tid = uuid.uuid4()
    rows = [(tid, "inbox", _config("inbox", description="v2 override description", version=2))]
    stamp = datetime(2026, 10, 14, tzinfo=UTC)
    session = _FakeSession(rows, fingerprint=(1, 2, stamp))
    assert await overrides.sync_registry(session, registry) is True  # type: ignore[arg-type]
    inbox = registry.get("inbox")
    assert inbox is not None and inbox.description == "v2 override description"
    assert await overrides.sync_registry(session, registry) is False  # type: ignore[arg-type]
    session.fingerprint = (1, 3, stamp)
    session.rows = [
        (tid, "inbox", _config("inbox", description="v3 override description", version=3))
    ]
    assert await overrides.sync_registry(session, registry) is True  # type: ignore[arg-type]
    inbox = registry.get("inbox")
    assert inbox is not None and inbox.description == "v3 override description"


async def test_sync_db_error_keeps_registry_and_does_not_raise(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload(overrides={"inbox": _config("inbox", description="kept override description")})
    before = registry.get("inbox")
    boom = OperationalError("select", {}, Exception("db down"))
    session = _FakeSession([], fingerprint=boom)
    assert await overrides.sync_registry(session, registry) is False  # type: ignore[arg-type]
    assert registry.get("inbox") == before
