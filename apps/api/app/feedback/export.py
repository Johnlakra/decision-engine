"""JSONL export of feedback for Laya fine-tuning and evals (FR-80; docs/LAYA.md sections 6, 7)."""

import json
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Feedback

ExportFormat = Literal["laya_train", "laya_eval"]
YIELD_PER = 200


def _expected(answers: Mapping[str, Mapping[str, float]]) -> dict[str, str]:
    return {qid: max(probs, key=lambda k: probs[k]) for qid, probs in answers.items() if probs}


def format_line(feedback: Feedback, fmt: ExportFormat) -> str | None:
    """One JSONL line, or None when the row has no usable labels. Never includes `raw`."""
    answers = ((feedback.gold or {}).get("answers")) or {}
    questions = feedback.questions or {}
    if not answers or not questions:
        return None
    record: dict[str, Any] = {"state": feedback.state_text, "questions": questions}
    if fmt == "laya_train":
        record["gold"] = answers
    else:
        record["expected"] = _expected(answers)
    return json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"


async def iter_export(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    niche: str | None,
    fmt: ExportFormat,
    since: datetime | None,
) -> AsyncIterator[str]:
    stmt = select(Feedback).where(Feedback.tenant_id == tenant_id).order_by(Feedback.created_at)
    if niche:
        stmt = stmt.where(Feedback.niche == niche)
    if since is not None:
        stmt = stmt.where(Feedback.created_at >= since)
    result = await session.stream_scalars(stmt.execution_options(yield_per=YIELD_PER))
    async for feedback in result:
        line = format_line(feedback, fmt)
        if line is not None:
            yield line
