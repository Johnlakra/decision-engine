"""P7: nothing ships with Laya mode ``on`` by default (FR-24, NFR-03). Needs no database."""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

REPO = Path(__file__).resolve().parents[5]
SCANNED = (".env.example", "docker-compose.yml", "apps/api/scripts", "niches", "data/seed")
ON_PATTERN = re.compile(r"""laya_mode["']?\s*[:=]\s*["']?on\b""", re.IGNORECASE)
TEXT_SUFFIXES = {"", ".py", ".yml", ".yaml", ".json", ".jsonl", ".example", ".env", ".sh", ".toml"}


def _files() -> list[Path]:
    found: list[Path] = []
    for name in SCANNED:
        path = REPO / name
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            found.extend(p for p in path.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    return found


def test_no_config_compose_script_or_niche_sets_laya_mode_on() -> None:
    offenders = [
        f"{path.relative_to(REPO)}:{number}"
        for path in _files()
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1)
        if ON_PATTERN.search(line)
    ]
    assert offenders == []


def test_scan_covers_the_files_that_exist() -> None:
    names = {path.name for path in _files()}
    assert ".env.example" in names and "docker-compose.yml" in names


def test_pattern_catches_the_forms_it_guards_against() -> None:
    for bad in ("LAYA_MODE=on", "laya_mode: on", 'laya_mode: "on"', "LAYA_MODE = 'on'"):
        assert ON_PATTERN.search(bad), bad
    for fine in ("LAYA_MODE=shadow", "# off | shadow | on", "laya_mode: off", "LAYA_MODE=one"):
        assert not ON_PATTERN.search(fine), fine


def test_settings_default_mode_is_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAYA_MODE", raising=False)
    assert Settings(_env_file=None).laya_mode == "shadow"  # type: ignore[call-arg]


def test_resolve_mode_defaults_to_shadow_without_tenant_settings() -> None:
    modes = pytest.importorskip("app.triage.modes")
    assert modes.resolve_mode({}, None, "shadow") == "shadow"
    assert modes.resolve_mode({}, "tech_stack", "shadow") == "shadow"
