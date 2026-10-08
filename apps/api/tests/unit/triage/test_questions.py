"""Core/niche questions and state_text (FR-20, FR-21)."""

import pytest

from app.niches.models import NicheConfig
from app.triage.questions import (
    QuestionError,
    core_questions,
    niche_questions,
    state_text,
    validate_questions,
)


def niche(name: str, **extra: object) -> NicheConfig:
    return NicheConfig.model_validate(
        {
            "name": name,
            "label": name,
            "description": f"things about {name}",
            "enabled": True,
            "prompt": "p",
            "actions": ["notify"],
            "autonomy": "ask",
            **extra,
        }
    )


def test_core_questions_cover_four_ids_with_niche_descriptions() -> None:
    questions = core_questions([niche("inbox"), niche("generic")])
    assert list(questions) == ["needs_decision", "niche", "urgency", "risk"]
    assert questions["niche"]["criteria"] == {
        "inbox": "things about inbox",
        "generic": "things about generic",
    }
    assert questions["urgency"]["type"] == "score"
    assert len(questions["urgency"]["criteria"]) == 3


def test_twelve_niches_ok_thirteen_error() -> None:
    assert core_questions([niche(f"n{i}") for i in range(12)])
    with pytest.raises(QuestionError, match="13"):
        core_questions([niche(f"n{i}") for i in range(13)])


def test_long_description_is_truncated_to_schema_limit() -> None:
    long = niche("big")
    long = long.model_copy(update={"description": "x" * 900})
    assert len(core_questions([long, niche("generic")])["niche"]["criteria"]["big"]) == 300


def test_niche_questions_returned_and_validated() -> None:
    n = niche(
        "inbox",
        triage={
            "questions": {
                "needs_reply": {
                    "type": "choice",
                    "instructions": "Reply expected?",
                    "criteria": {"A": "yes", "B": "no"},
                }
            }
        },
    )
    assert list(niche_questions(n)) == ["needs_reply"]


def test_invalid_question_rejected() -> None:
    with pytest.raises(QuestionError):
        validate_questions(
            {"q": {"type": "choice", "instructions": "hello there", "criteria": {"A": "x"}}}
        )
    with pytest.raises(QuestionError):
        validate_questions({"q": {"type": "choice", "instructions": "hello there"}})


def test_more_than_twelve_options_rejected() -> None:
    criteria = {f"k{i}": "x" for i in range(13)}
    with pytest.raises(QuestionError, match="13"):
        validate_questions(
            {"q": {"type": "choice", "instructions": "pick one", "criteria": criteria}}
        )


def test_state_text_shape_caps_body_and_cleans_control_chars() -> None:
    text = state_text({"title": "Hi\x00 there", "sender": "a@b.c", "body": "z" * 2000})
    assert text.startswith("Subject: Hi there\nFrom: a@b.c\n\n")
    assert text.count("z") == 600


def test_state_text_without_sender_or_body() -> None:
    assert state_text({"title": "Only"}) == "Subject: Only"
