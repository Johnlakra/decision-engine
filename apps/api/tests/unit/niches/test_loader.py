"""Niche loader tests (FR-70)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import REPO_ROOT
from app.niches.loader import NicheValidationError, load_niche_file
from app.niches.models import NicheConfig

SCHEMAS = REPO_ROOT / "schemas"
NICHES = REPO_ROOT / "niches"
STARTERS = sorted(p for p in NICHES.glob("*.yaml"))


def good(name: str = "demo") -> dict[str, Any]:
    return {
        "name": name,
        "label": "Demo",
        "description": "a demo niche used only by tests",
        "enabled": True,
        "prompt": "Help the owner with one demo item. Never invent facts; say what is missing.",
        "actions": ["draft_reply"],
        "autonomy": "ask",
    }


def write(tmp_path: Path, data: dict[str, Any], name: str | None = None) -> Path:
    path = tmp_path / f"{name or data['name']}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def question(**over: Any) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": "Is it urgent?",
        "criteria": {"A": "yes", "B": "no"},
    } | over


def test_five_starter_niches_exist() -> None:
    assert len(STARTERS) == 5


@pytest.mark.parametrize("path", STARTERS, ids=lambda p: p.stem)
def test_starter_niche_validates(path: Path) -> None:
    cfg = load_niche_file(path, SCHEMAS)
    assert cfg.name == path.stem


def _walk_defaults(schema: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, sub in schema.get("properties", {}).items():
        if "default" in sub:
            out[key] = sub["default"]
        elif sub.get("type") == "object" and "properties" in sub:
            nested = _walk_defaults(sub)
            if nested:
                out[key] = nested
    return out


def test_pydantic_defaults_equal_schema_defaults(tmp_path: Path) -> None:
    schema = json.loads((SCHEMAS / "niche.schema.json").read_text())
    expected = _walk_defaults(schema)
    assert expected["notify"] and expected["triage"] and expected["llm"] and expected["version"]
    dumped = load_niche_file(write(tmp_path, good()), SCHEMAS).model_dump()

    def check(exp: dict[str, Any], got: dict[str, Any], where: str) -> None:
        for key, val in exp.items():
            if isinstance(val, dict):
                check(val, got[key], f"{where}.{key}")
            else:
                assert got[key] == val, f"{where}.{key}"

    check(expected, dumped, "niche")
    assert isinstance(NicheConfig.model_validate(good()), NicheConfig)


def test_auto_without_auto_actions_rejected(tmp_path: Path) -> None:
    with pytest.raises(NicheValidationError):
        load_niche_file(write(tmp_path, good() | {"autonomy": "auto"}), SCHEMAS)


def test_auto_with_auto_actions_accepted(tmp_path: Path) -> None:
    data = good() | {"autonomy": "auto", "auto_actions": ["label"]}
    assert load_niche_file(write(tmp_path, data), SCHEMAS).auto_actions == ["label"]


def test_bad_ref_question_rejected(tmp_path: Path) -> None:
    data = good() | {"triage": {"questions": {"q": question(type="bogus")}}}
    with pytest.raises(NicheValidationError) as exc:
        load_niche_file(write(tmp_path, data), SCHEMAS)
    assert exc.value.json_pointer.startswith("/triage/questions/q")
    assert exc.value.file == "demo.yaml"


def test_question_missing_criteria_rejected(tmp_path: Path) -> None:
    bad = {"type": "choice", "instructions": "Is it urgent?"}
    with pytest.raises(NicheValidationError):
        load_niche_file(write(tmp_path, good() | {"triage": {"questions": {"q": bad}}}), SCHEMAS)


def test_more_than_eight_questions_rejected(tmp_path: Path) -> None:
    qs = {f"q{i}": question() for i in range(9)}
    with pytest.raises(NicheValidationError) as exc:
        load_niche_file(write(tmp_path, good() | {"triage": {"questions": qs}}), SCHEMAS)
    assert exc.value.json_pointer == "/triage/questions"


def test_eight_questions_accepted(tmp_path: Path) -> None:
    qs = {f"q{i}": question() for i in range(8)}
    cfg = load_niche_file(write(tmp_path, good() | {"triage": {"questions": qs}}), SCHEMAS)
    assert len(cfg.triage.questions) == 8


def test_file_name_must_equal_name(tmp_path: Path) -> None:
    with pytest.raises(NicheValidationError) as exc:
        load_niche_file(write(tmp_path, good("demo"), name="other"), SCHEMAS)
    assert exc.value.json_pointer == "/name"


def test_unknown_field_rejected(tmp_path: Path) -> None:
    with pytest.raises(NicheValidationError):
        load_niche_file(write(tmp_path, good() | {"surprise": 1}), SCHEMAS)


def test_broken_yaml_rejected(tmp_path: Path) -> None:
    path = tmp_path / "demo.yaml"
    path.write_text("name: [unclosed", encoding="utf-8")
    with pytest.raises(NicheValidationError):
        load_niche_file(path, SCHEMAS)


def test_non_mapping_rejected(tmp_path: Path) -> None:
    path = tmp_path / "demo.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(NicheValidationError):
        load_niche_file(path, SCHEMAS)
