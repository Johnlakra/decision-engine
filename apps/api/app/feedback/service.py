"""Write one feedback row per decision (FR-54). Contract C8."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.models import Feedback, Item
from app.models.enums import DecidedBy, FeedbackKind, LabelSource, Verdict
from app.schemas.decision import DecisionIn
from app.triage.questions import state_text

STATE_CAP = 700  # DATA_MODEL.md: feedback state_text truncated for training


def _answer_gold(answer: Mapping[str, Any]) -> dict[str, float] | None:
    """Hard label 1.0 on the chosen key; None when the answer has no usable key."""
    if answer.get("choice") is not None:
        return {str(answer["choice"]): 1.0}
    if answer.get("level") is not None:
        return {str(answer["level"]): 1.0}
    return None


def build_gold(
    triage: Mapping[str, Any] | None, body: DecisionIn, latency_ms: int | None
) -> dict[str, Any]:
    answers: dict[str, dict[str, float]] = {}
    for qid, answer in ((triage or {}).get("answers") or {}).items():
        gold = _answer_gold(answer) if isinstance(answer, Mapping) else None
        if gold is not None:
            answers[str(qid)] = gold
    decision: dict[str, Any] = {
        "verdict": str(body.verdict.value if hasattr(body.verdict, "value") else body.verdict),
        "option": body.option,
        "edited": body.verdict == Verdict.EDIT or bool(body.edits),
    }
    if latency_ms is not None:
        decision["latency_ms"] = latency_ms
    return {"answers": answers, "decision": decision}


async def record_decision_feedback(
    session: AsyncSession,
    *,
    item: Item,
    body: DecisionIn,
    decided_by: DecidedBy,
    latency_ms: int | None,
) -> Feedback:
    """Add a `decision` feedback row (caller commits)."""
    triage = item.triage or {}
    feedback = Feedback(
        id=new_id(),
        tenant_id=item.tenant_id,
        item_id=item.id,
        niche=item.niche,
        kind=FeedbackKind.DECISION.value,
        state_text=state_text(item.content or {"title": ""})[:STATE_CAP],
        questions=triage.get("questions") or {},
        gold=build_gold(triage, body, latency_ms),
        label_source=(
            LabelSource.HUMAN.value if decided_by == DecidedBy.HUMAN else LabelSource.LLM.value
        ),
    )
    session.add(feedback)
    await session.flush()
    return feedback
