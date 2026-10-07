"""Niche registry tests (FR-71)."""

import shutil
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT
from app.niches.registry import MissingGenericNicheError, NicheRegistry, get_registry

SCHEMAS = REPO_ROOT / "schemas"


@pytest.fixture
def niches_dir(tmp_path: Path) -> Path:
    target = tmp_path / "niches"
    shutil.copytree(REPO_ROOT / "niches", target)
    return target


def test_reload_loads_all_starters(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    result = registry.reload()
    assert result.errors == []
    assert "generic" in result.loaded and len(result.loaded) == 5
    assert registry.get("generic") is not None
    assert registry.get("nope") is None
    assert {n.name for n in registry.enabled()} <= set(result.loaded)


def test_invalid_file_keeps_previous_version(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    before = registry.get("inbox")
    assert before is not None
    path = niches_dir / "inbox.yaml"
    path.write_text(path.read_text().replace("autonomy: ask", "autonomy: auto"))
    result = registry.reload()
    assert [e.file for e in result.errors] == ["inbox.yaml"]
    assert registry.errors == result.errors
    assert registry.get("inbox") == before
    assert "inbox" in result.loaded


def test_fixed_file_clears_errors(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    path = niches_dir / "inbox.yaml"
    original = path.read_text()
    path.write_text("name: [broken")
    assert registry.reload().errors
    path.write_text(original)
    assert registry.reload().errors == []
    assert registry.errors == []


def test_new_invalid_file_not_loaded(niches_dir: Path) -> None:
    (niches_dir / "extra.yaml").write_text("name: extra\n")
    registry = NicheRegistry(niches_dir, SCHEMAS)
    result = registry.reload()
    assert registry.get("extra") is None
    assert [e.file for e in result.errors] == ["extra.yaml"]


def test_missing_generic_is_hard_error(niches_dir: Path) -> None:
    (niches_dir / "generic.yaml").unlink()
    registry = NicheRegistry(niches_dir, SCHEMAS)
    with pytest.raises(MissingGenericNicheError):
        registry.reload()
    assert any(e.file == "generic.yaml" for e in registry.errors)


def test_generic_removed_later_keeps_previous_and_reports(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    (niches_dir / "generic.yaml").unlink()
    result = registry.reload()
    assert any(e.file == "generic.yaml" for e in result.errors)
    assert registry.get("generic") is not None


def test_removed_file_drops_niche(niches_dir: Path) -> None:
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    (niches_dir / "news_radar.yaml").unlink()
    registry.reload()
    assert registry.get("news_radar") is None


def test_disabled_niche_excluded_from_enabled(niches_dir: Path) -> None:
    path = niches_dir / "inbox.yaml"
    path.write_text(path.read_text().replace("enabled: true", "enabled: false"))
    registry = NicheRegistry(niches_dir, SCHEMAS)
    registry.reload()
    assert "inbox" not in [n.name for n in registry.enabled()]


def test_get_registry_is_singleton() -> None:
    assert get_registry() is get_registry()
    assert get_registry().get("generic") is not None
