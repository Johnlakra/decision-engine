"""Shadow report: how Laya would have done per confidence cutoff (FR-81, docs/LAYA.md).

For each human-labelled answer (feedback ``gold``) that Laya also answered in shadow mode, it asks:
at cutoff ``c``, would Laya have decided (confidence >= c), and was that decision right?
Usage: ``python -m app.feedback.shadow_report --niche news_radar --days 14``.
"""

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Feedback, Item
from app.models.enums import FeedbackKind
from app.schemas.triage import Answer

CUTOFFS = (0.5, 0.6, 0.7, 0.8, 0.9)
DEFAULT_DAYS = 14


@dataclass(frozen=True)
class ShadowSample:
    """One labelled question: the human choice and what Laya said in shadow mode."""

    question: str
    human_choice: str
    shadow_choice: str | None
    shadow_confidence: float | None


@dataclass(frozen=True)
class CutoffRow:
    cutoff: float
    labelled: int
    decided: int
    agreed: int
    wrong: int

    @property
    def skipped(self) -> int:
        """Labelled answers Laya would have left to the fallback or a human."""
        return self.labelled - self.decided


def _decides_at(sample: ShadowSample, cutoff: float) -> bool:
    return (
        sample.shadow_choice is not None
        and sample.shadow_confidence is not None
        and sample.shadow_confidence >= cutoff
    )


def summarize(
    samples: Sequence[ShadowSample], cutoffs: Sequence[float] = CUTOFFS
) -> list[CutoffRow]:
    rows: list[CutoffRow] = []
    for cutoff in cutoffs:
        decided = [sample for sample in samples if _decides_at(sample, cutoff)]
        agreed = [sample for sample in decided if sample.shadow_choice == sample.human_choice]
        rows.append(
            CutoffRow(
                cutoff=cutoff,
                labelled=len(samples),
                decided=len(decided),
                agreed=len(agreed),
                wrong=len(decided) - len(agreed),
            )
        )
    return rows


def _human_choice(gold_answers: Any) -> dict[str, str]:
    """Hard label per question from ``feedback.gold['answers']``: the key with weight 1.0."""
    labels: dict[str, str] = {}
    if not isinstance(gold_answers, Mapping):
        return labels
    for question, weights in gold_answers.items():
        if isinstance(weights, Mapping) and weights:
            labels[str(question)] = max(weights, key=lambda key: float(weights[key]))
    return labels


def _shadow_answers(triage: Any) -> dict[str, Answer]:
    """Shadow answers validated against the Answer schema; malformed entries are ignored."""
    if not isinstance(triage, Mapping):
        return {}
    shadow = triage.get("shadow")
    raw = shadow.get("answers") if isinstance(shadow, Mapping) else None
    if not isinstance(raw, Mapping):
        return {}
    parsed: dict[str, Answer] = {}
    for question, value in raw.items():
        try:
            parsed[str(question)] = Answer.model_validate(value)
        except ValidationError:
            continue
    return parsed


def samples_for(feedback_gold: Any, triage: Any) -> list[ShadowSample]:
    """Pair each human label with the shadow answer for the same question."""
    shadow = _shadow_answers(triage)
    samples: list[ShadowSample] = []
    for question, human in _human_choice(feedback_gold).items():
        answer = shadow.get(question)
        if answer is None:
            continue
        samples.append(
            ShadowSample(
                question=question,
                human_choice=human,
                shadow_choice=answer.choice,
                shadow_confidence=answer.confidence,
            )
        )
    return samples


async def collect_samples(session: AsyncSession, niche: str, days: int) -> list[ShadowSample]:
    since = utcnow() - timedelta(days=days)
    stmt = (
        select(Feedback.gold, Item.triage)
        .join(Item, Item.id == Feedback.item_id)
        .where(
            Feedback.niche == niche,
            Feedback.kind == FeedbackKind.DECISION.value,
            Feedback.created_at >= since,
        )
    )
    samples: list[ShadowSample] = []
    for gold, triage in (await session.execute(stmt)).all():
        samples.extend(samples_for(gold, triage))
    return samples


def format_table(niche: str, days: int, rows: Sequence[CutoffRow]) -> str:
    header = f"shadow report: niche={niche} last {days} days"
    lines = [
        header,
        f"{'cutoff':>7} {'labelled':>9} {'decided':>8} {'agreed':>7} {'wrong':>6} {'skipped':>8}",
    ]
    for row in rows:
        lines.append(
            f"{row.cutoff:>7.2f} {row.labelled:>9} {row.decided:>8} "
            f"{row.agreed:>7} {row.wrong:>6} {row.skipped:>8}"
        )
    return "\n".join(lines)


async def run(niche: str, days: int) -> list[CutoffRow]:
    async with session_scope() as session:
        samples = await collect_samples(session, niche, days)
    return summarize(samples)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Laya shadow report per confidence cutoff.")
    parser.add_argument("--niche", required=True, help="niche name, e.g. news_radar")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="look-back window")
    args = parser.parse_args(argv)
    if args.days < 1:
        parser.error("--days must be at least 1")
    rows = asyncio.run(run(args.niche, args.days))
    print(format_table(args.niche, args.days, rows))  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
