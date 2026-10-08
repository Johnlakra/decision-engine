"""DB access for graph nodes. Every function opens its own short session (C7).

Nodes call these through the module (``store.load_item_view``) so unit tests can replace them.
Status changes go only through ``models.status.transition`` and are guarded by the current status,
so a node that re-runs after a crash or an interrupt resume is a no-op the second time.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.models import Item
from app.models.enums import ItemStatus
from app.models.feedback import Feedback
from app.models.status import transition


@dataclass(frozen=True)
class ItemView:
    id: str
    tenant_id: str
    status: str
    source: str
    sensitivity: str
    language: str
    niche: str | None
    risk: str | None
    triage: dict[str, Any] | None
    content: dict[str, Any] = field(default_factory=dict)
    decision: dict[str, Any] | None = None


@dataclass(frozen=True)
class Correction:
    state_text: str
    verdict: str | None
    option: str | None
    edited: bool


def _view(item: Item) -> ItemView:
    return ItemView(
        id=str(item.id),
        tenant_id=str(item.tenant_id),
        status=item.status,
        source=item.source,
        sensitivity=item.sensitivity,
        language=item.language or "en",
        niche=item.niche,
        risk=item.risk,
        triage=dict(item.triage) if item.triage else None,
        content=dict(item.content) if item.content else {},
        decision=dict(item.decision) if item.decision else None,
    )


async def _locked(session: AsyncSession, item_id: str) -> Item:
    stmt = select(Item).where(Item.id == uuid.UUID(item_id)).with_for_update()
    return (await session.scalars(stmt)).one()


async def load_item_view(item_id: str) -> ItemView:
    async with session_scope() as session:
        item = (await session.scalars(select(Item).where(Item.id == uuid.UUID(item_id)))).one()
        return _view(item)


async def apply_route(item_id: str, *, niche: str, informational: bool) -> None:
    """Record the routed niche and move ``triaged -> informational | deciding``."""
    async with session_scope() as session:
        item = await _locked(session, item_id)
        item.niche = niche
        if item.status == ItemStatus.TRIAGED:
            target = ItemStatus.INFORMATIONAL if informational else ItemStatus.DECIDING
            transition(item, target)


async def save_entities(item_id: str, entities: dict[str, Any]) -> None:
    async with session_scope() as session:
        item = await _locked(session, item_id)
        item.content = {**(item.content or {}), "entities": entities}


async def save_decision(item_id: str, decision: dict[str, Any]) -> None:
    """Persist ``items.decision`` while the item is still being decided."""
    async with session_scope() as session:
        item = await _locked(session, item_id)
        if item.status == ItemStatus.DECIDING:
            item.decision = decision


async def load_corrections(tenant_id: str, niche: str, limit: int) -> list[Correction]:
    """The last ``limit`` human decisions for this niche, newest first (few-shot, FR-62)."""
    if limit <= 0:
        return []
    stmt = (
        select(Feedback)
        .where(
            Feedback.tenant_id == uuid.UUID(tenant_id),
            Feedback.niche == niche,
            Feedback.kind == "decision",
        )
        .order_by(Feedback.created_at.desc())
        .limit(limit)
    )
    async with session_scope() as session:
        rows = (await session.scalars(stmt)).all()
    corrections: list[Correction] = []
    for row in rows:
        decision = (row.gold or {}).get("decision") or {}
        corrections.append(
            Correction(
                state_text=row.state_text,
                verdict=decision.get("verdict"),
                option=decision.get("option"),
                edited=bool(decision.get("edited")),
            )
        )
    return corrections
