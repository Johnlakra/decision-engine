"""C1 decision schemas (FR-33, FR-35)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import Verdict
from app.schemas.decision import DecisionIn, DecisionOut, StoredDecision


def _opts(*ids: str) -> list[dict[str, Any]]:
    return [{"id": i, "label": f"Option {i}"} for i in ids]


def _out(options: list[dict[str, Any]] | None = None, recommended: str = "A") -> dict[str, Any]:
    return {
        "options": options or _opts("A", "B"),
        "recommended": recommended,
        "rationale": "because",
        "confidence": 0.8,
    }


def test_valid_decision_out() -> None:
    out = DecisionOut.model_validate(_out())
    assert out.recommended == "A"
    assert out.evidence == []


@pytest.mark.parametrize("ids", [("A",), ("A", "B", "C", "D", "E", "A")])
def test_rejects_wrong_option_count(ids: tuple[str, ...]) -> None:
    with pytest.raises(ValidationError):
        DecisionOut.model_validate(_out(_opts(*ids)))


def test_rejects_six_distinct_option_ids() -> None:
    with pytest.raises(ValidationError):
        DecisionOut.model_validate(_out(_opts("A", "B", "C", "D", "E", "F")))


def test_rejects_duplicate_option_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        DecisionOut.model_validate(_out(_opts("A", "A")))


def test_rejects_recommended_not_an_option() -> None:
    with pytest.raises(ValidationError, match="recommended"):
        DecisionOut.model_validate(_out(recommended="C"))


def test_rejects_long_rationale_and_bad_confidence() -> None:
    with pytest.raises(ValidationError):
        DecisionOut.model_validate({**_out(), "rationale": "x" * 601})
    with pytest.raises(ValidationError):
        DecisionOut.model_validate({**_out(), "confidence": 1.5})


def test_stored_decision_extends_out() -> None:
    stored = StoredDecision.model_validate(
        {**_out(), "autonomy": "ask", "model": None, "niche_version": 1}
    )
    assert stored.needs_expert is False
    assert stored.warnings == []


def test_snooze_requires_future_snooze_until() -> None:
    with pytest.raises(ValidationError, match="snooze_until"):
        DecisionIn(verdict=Verdict.SNOOZE)
    with pytest.raises(ValidationError, match="snooze_until"):
        DecisionIn(verdict=Verdict.SNOOZE, snooze_until=datetime.now(UTC) - timedelta(minutes=1))
    ok = DecisionIn(verdict=Verdict.SNOOZE, snooze_until=datetime.now(UTC) + timedelta(hours=1))
    assert ok.snooze_until is not None


def test_approve_needs_no_snooze_and_note_is_capped() -> None:
    assert DecisionIn(verdict=Verdict.APPROVE, option="A").snooze_until is None
    with pytest.raises(ValidationError):
        DecisionIn(verdict=Verdict.APPROVE, note="x" * 1001)
