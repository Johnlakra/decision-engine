"""Feedback gold and JSONL formats (FR-54, FR-80)."""

import json
import uuid
from typing import Any

from app.feedback import service
from app.feedback.export import format_line
from app.models import Feedback, Item
from app.models.enums import DecidedBy, Verdict
from app.schemas.decision import DecisionIn

QUESTIONS = {
    "needs_decision": {"type": "choice", "instructions": "x?", "criteria": {"A": "y", "B": "n"}}
}
TRIAGE: dict[str, Any] = {
    "questions": QUESTIONS,
    "answers": {
        "needs_decision": {"type": "choice", "choice": "A", "probabilities": {"A": 0.7}},
        "urgency": {"type": "score", "level": 2, "score": 1.6},
        "flag": {"type": "noul", "noul": 0.4},
    },
}


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def make_item() -> Item:
    return Item(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        niche="inbox",
        triage=TRIAGE,
        content={"title": "T", "body": "b" * 5000, "sender": "s@x"},
        raw={"secret": "do-not-leak"},
    )


async def test_record_decision_feedback_builds_gold_and_caps_state() -> None:
    session, item = FakeSession(), make_item()
    body = DecisionIn(verdict=Verdict.EDIT, option="A", edits={"x": 1})
    fb = await service.record_decision_feedback(
        session,  # type: ignore[arg-type]
        item=item,
        body=body,
        decided_by=DecidedBy.HUMAN,
        latency_ms=1200,
    )
    assert session.added == [fb]
    assert fb.gold["answers"] == {"needs_decision": {"A": 1.0}, "urgency": {"2": 1.0}}
    assert fb.gold["decision"] == {
        "verdict": "edit",
        "option": "A",
        "edited": True,
        "latency_ms": 1200,
    }
    assert len(fb.state_text) <= 700 and fb.questions == QUESTIONS
    assert (fb.kind, fb.label_source, fb.niche) == ("decision", "human", "inbox")


async def test_auto_decision_is_labelled_llm() -> None:
    fb = await service.record_decision_feedback(
        FakeSession(),  # type: ignore[arg-type]
        item=make_item(),
        body=DecisionIn(verdict=Verdict.APPROVE, option="A"),
        decided_by=DecidedBy.AUTO,
        latency_ms=None,
    )
    assert fb.label_source == "llm" and fb.gold["decision"]["edited"] is False
    assert "latency_ms" not in fb.gold["decision"]


def feedback() -> Feedback:
    return Feedback(
        state_text="Subject: T",
        questions=QUESTIONS,
        gold={"answers": {"needs_decision": {"A": 1.0}}, "decision": {}},
    )


def test_laya_train_line_has_gold_probabilities_and_no_raw() -> None:
    line = format_line(feedback(), "laya_train")
    assert line is not None and line.endswith("\n")
    assert json.loads(line) == {
        "state": "Subject: T",
        "questions": QUESTIONS,
        "gold": {"needs_decision": {"A": 1.0}},
    }
    assert "raw" not in line and "do-not-leak" not in line


def test_laya_eval_line_has_expected_keys() -> None:
    line = format_line(feedback(), "laya_eval")
    assert line is not None
    assert json.loads(line) == {
        "state": "Subject: T",
        "questions": QUESTIONS,
        "expected": {"needs_decision": "A"},
    }


def test_rows_without_labels_are_skipped() -> None:
    empty = Feedback(state_text="s", questions=QUESTIONS, gold={"answers": {}})
    assert format_line(empty, "laya_train") is None
