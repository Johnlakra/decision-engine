"""C1 content and triage schemas (FR-10, FR-21)."""

import pytest
from pydantic import ValidationError

from app.schemas.content import NormalisedContent
from app.schemas.triage import Answer, ShadowRecord, TriageRecord


def test_content_defaults_and_title_cap() -> None:
    content = NormalisedContent(title="Hi")
    assert content.body == ""
    assert content.entities == {}
    assert content.flags == []
    with pytest.raises(ValidationError):
        NormalisedContent(title="x" * 501)


def test_answer_types() -> None:
    a = Answer(type="choice", choice="yes", probabilities={"yes": 0.9}, source="laya")
    assert a.confidence is None
    with pytest.raises(ValidationError):
        Answer(type="other", source="laya")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Answer(type="choice", source="bogus")  # type: ignore[arg-type]


def test_triage_record_round_trip() -> None:
    answer = Answer(type="score", score=0.5, level=1, source="llm_fallback")
    record = TriageRecord(
        mode="shadow", model="m", laya_version="1", fallback=True, decided_by="llm_fallback",
        answers={"urgency": answer}, questions={"urgency": {"type": "score"}},
        shadow=ShadowRecord(answers=None, model=None, latency_ms=None, error="down"),
        latency_ms=12, error=None,
    )  # fmt: skip
    again = TriageRecord.model_validate(record.model_dump(mode="json"))
    assert again == record
