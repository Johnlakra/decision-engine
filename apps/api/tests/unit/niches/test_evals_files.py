"""Eval files for generic and tech_stack (FR-73, docs/LAYA.md section 6)."""

import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.core.config import REPO_ROOT

EVALS = REPO_ROOT / "evals"
NICHES = REPO_ROOT / "niches"
SCHEMAS = REPO_ROOT / "schemas"
NAMES = ["generic", "tech_stack"]
MIN_ROWS = 30
LANGUAGES = {"en", "hi", "hinglish", "pa"}


def rows(name: str) -> list[dict[str, Any]]:
    lines = (EVALS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def question_validator() -> Draft202012Validator:
    schema = json.loads((SCHEMAS / "laya_question.schema.json").read_text())
    return Draft202012Validator(
        schema, registry=Registry().with_resource(schema["$id"], Resource.from_contents(schema))
    )


def descriptions() -> dict[str, str]:
    out = {}
    for path in NICHES.glob("*.yaml"):
        cfg = yaml.safe_load(path.read_text())
        out[cfg["name"]] = cfg["description"]
    return out


@pytest.mark.parametrize("name", NAMES)
def test_row_count_and_format(name: str) -> None:
    data = rows(name)
    assert len(data) >= MIN_ROWS
    for row in data:
        assert set(row) == {"state", "questions", "expected", "tags", "language"}
        assert row["state"].strip()
        assert row["language"] in LANGUAGES
        assert name in row["tags"]


@pytest.mark.parametrize("name", NAMES)
def test_questions_valid_and_expected_keys_in_criteria(name: str) -> None:
    validator = question_validator()
    for row in rows(name):
        assert set(row["expected"]) == set(row["questions"])
        for qid, question in row["questions"].items():
            validator.validate(question)
            assert row["expected"][qid] in question["criteria"], (qid, row["state"])


@pytest.mark.parametrize("name", NAMES)
def test_niche_criteria_match_current_descriptions(name: str) -> None:
    known = descriptions()
    for row in rows(name):
        for key, text in row["questions"]["niche"]["criteria"].items():
            assert known[key] == text


@pytest.mark.parametrize("name", NAMES)
def test_balanced_and_multilingual(name: str) -> None:
    data = rows(name)
    niche = [r["expected"]["niche"] for r in data]
    for label in ("generic", "tech_stack"):
        assert niche.count(label) >= len(data) * 0.3, label
    decision = [r["expected"]["needs_decision"] for r in data]
    assert decision.count("B") >= 3
    assert any(r["language"] != "en" for r in data)
    assert any("near_miss" in r["tags"] for r in data)
    assert len({r["state"] for r in data}) == len(data)


def test_generic_covers_punjabi() -> None:
    assert any(r["language"] == "pa" for r in rows("generic"))
