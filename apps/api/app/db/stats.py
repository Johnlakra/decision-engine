"""Read-only counters behind GET /v1/stats/today (FR-60, FR-64). Day = UTC day."""

import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.config import LLMConfig
from app.models import Decision, Item, LlmUsage
from app.models.enums import DecidedBy, ItemStatus
from app.schemas.stats import LlmBudgetOut

UNASSIGNED = "unassigned"
MAX_AGREEMENT_ITEMS = 5000  # newest shadow rows read per request


async def _count(session: AsyncSession, *conditions: Any) -> int:
    stmt = select(func.count()).select_from(conditions[0]).where(*conditions[1:])
    return int((await session.execute(stmt)).scalar_one())


async def item_counts(
    session: AsyncSession, tenant_id: uuid.UUID, since: datetime
) -> dict[str, Any]:
    created = (Item.tenant_id == tenant_id, Item.created_at >= since)
    by_status = (
        await session.execute(
            select(Item.status, func.count()).where(*created).group_by(Item.status)
        )
    ).all()
    by_niche = (
        await session.execute(select(Item.niche, func.count()).where(*created).group_by(Item.niche))
    ).all()
    discarded = await _count(
        session,
        Item,
        Item.tenant_id == tenant_id,
        Item.status == ItemStatus.DISCARDED.value,
        func.coalesce(Item.updated_at, Item.created_at) >= since,
    )
    niches: dict[str, int] = {}
    for niche, count in by_niche:
        key = niche or UNASSIGNED
        niches[key] = niches.get(key, 0) + int(count)
    statuses = {status: int(count) for status, count in by_status}
    return {
        "items_in": sum(statuses.values()),
        "discarded": discarded,
        "by_status": dict(sorted(statuses.items())),
        "by_niche": dict(sorted(niches.items())),
    }


async def decision_counts(
    session: AsyncSession, tenant_id: uuid.UUID, since: datetime
) -> tuple[int, int]:
    """(human decisions, auto decisions) made today and not undone."""
    stmt = (
        select(Decision.decided_by, func.count())
        .where(
            Decision.tenant_id == tenant_id,
            Decision.created_at >= since,
            Decision.undone_at.is_(None),
        )
        .group_by(Decision.decided_by)
    )
    counts = {by: int(n) for by, n in (await session.execute(stmt)).all()}
    return counts.get(DecidedBy.HUMAN.value, 0), counts.get(DecidedBy.AUTO.value, 0)


async def llm_budgets(
    session: AsyncSession, tenant_id: uuid.UUID, since: datetime, config: LLMConfig
) -> list[LlmBudgetOut]:
    """Per provider: requests and tokens used today (llm_usage) against the configured limits."""
    stmt = (
        select(
            LlmUsage.provider,
            func.count(),
            func.coalesce(func.sum(LlmUsage.prompt_tokens + LlmUsage.completion_tokens), 0),
        )
        .where(LlmUsage.tenant_id == tenant_id, LlmUsage.created_at >= since)
        .group_by(LlmUsage.provider)
    )
    used = {name: (int(n), int(tokens)) for name, n, tokens in (await session.execute(stmt)).all()}
    names = sorted({*used, *(n for n, p in config.providers.items() if p.available)})
    rows = []
    for name in names:
        provider = config.providers.get(name)
        requests, tokens = used.get(name, (0, 0))
        rows.append(
            LlmBudgetOut(
                provider=name,
                requests_used=requests,
                requests_limit=provider.rpd if provider else None,
                tokens_used=tokens,
                tokens_limit=provider.tpd if provider else None,
            )
        )
    return rows


def _choices(answers: object) -> dict[str, str]:
    if not isinstance(answers, Mapping):
        return {}
    out: dict[str, str] = {}
    for question, answer in answers.items():
        choice = answer.get("choice") if isinstance(answer, Mapping) else None
        if isinstance(choice, str):
            out[str(question)] = choice
    return out


def laya_agreement(pairs: Iterable[tuple[object, object]]) -> float | None:
    """Share of questions where Laya's shadow choice equals the answer that was used.

    ``pairs`` are (triage.answers, triage.shadow.answers). Questions answered by only one side
    or without a choice are skipped. None when nothing is comparable.
    """
    agreed = total = 0
    for used, shadow in pairs:
        own, theirs = _choices(used), _choices(shadow)
        for question, choice in theirs.items():
            if question in own:
                total += 1
                agreed += int(own[question] == choice)
    return agreed / total if total else None


async def shadow_agreement(
    session: AsyncSession, tenant_id: uuid.UUID, since: datetime
) -> float | None:
    stmt = (
        select(Item.triage["answers"], Item.triage["shadow"]["answers"])
        .where(
            Item.tenant_id == tenant_id,
            Item.created_at >= since,
            Item.triage["shadow"]["answers"].is_not(None),
        )
        .order_by(Item.created_at.desc())
        .limit(MAX_AGREEMENT_ITEMS)
    )
    rows = (await session.execute(stmt)).all()
    return laya_agreement((used, shadow) for used, shadow in rows)
