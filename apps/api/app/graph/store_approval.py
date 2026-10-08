"""DB access for the approval, act and finish nodes (C7). Each function is one short transaction.

Every write is guarded by the current ``items.status`` so a node that re-runs after a crash or an
interrupt resume does nothing the second time. ``transition`` stays the only status writer.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import ActionContext, run_action
from app.core.ids import new_id
from app.core.time import utcnow
from app.db.session import session_scope
from app.feedback.service import record_decision_feedback
from app.graph.errors import InvalidDecision, NotAwaitingApproval
from app.graph.store import _locked
from app.integrations.events import emit
from app.models import Decision, Item
from app.models.enums import DecidedBy, ItemStatus, JobKind, Verdict
from app.models.status import transition
from app.schemas.decision import DecisionIn
from app.workers import queue

_TARGET = {
    Verdict.APPROVE: ItemStatus.APPROVED,
    Verdict.EDIT: ItemStatus.APPROVED,
    Verdict.REJECT: ItemStatus.REJECTED,
    Verdict.SNOOZE: ItemStatus.SNOOZED,
}
UNSNOOZE_OP = "unsnooze"


def _verdict_json(
    row_verdict: str, option: str | None, edits: dict[str, Any] | None, decided_by: str
) -> dict[str, Any]:
    return {"verdict": row_verdict, "option": option, "edits": edits, "decided_by": decided_by}


def _latency_ms(decision: dict[str, Any] | None) -> int | None:
    ready = (decision or {}).get("ready_at")
    if not ready:
        return None
    return max(int((utcnow() - datetime.fromisoformat(str(ready))).total_seconds() * 1000), 0)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def mark_ready(item_id: str, *, announce: bool) -> dict[str, Any]:
    """``deciding -> awaiting_approval``: stamp ``ready_at`` and emit ``decision.ready``."""
    async with session_scope() as session:
        item = await _locked(session, item_id)
        decision = dict(item.decision or {})
        if item.status == ItemStatus.DECIDING:
            decision["ready_at"] = utcnow().isoformat()
            item.decision = decision
            transition(item, ItemStatus.AWAITING_APPROVAL)
            if announce:
                await emit(
                    session, tenant_id=item.tenant_id, event="decision.ready", item_id=item.id
                )
        return decision


def _resolve_option(item: Item, body: DecisionIn) -> str | None:
    decision = item.decision or {}
    ids = [o["id"] for o in decision.get("options", [])]
    if body.verdict in (Verdict.APPROVE, Verdict.EDIT):
        option = body.option or decision.get("recommended")
    else:
        option = body.option
    if option is not None and option not in ids:
        raise InvalidDecision(f"option {option!r} is not one of {ids}")
    return option


async def _replayed(session: AsyncSession, item: Item) -> dict[str, Any]:
    """The already recorded verdict (node re-ran after its write committed)."""
    stmt = (
        select(Decision)
        .where(Decision.item_id == item.id)
        .order_by(Decision.created_at.desc(), Decision.id.desc())
        .limit(1)
    )
    row = (await session.scalars(stmt)).first()
    if row is None:
        raise NotAwaitingApproval(f"item is {item.status}, not awaiting approval")
    return _verdict_json(row.verdict, row.option, row.edits, row.decided_by)


async def record_verdict(
    item_id: str, body: DecisionIn, *, decided_by: DecidedBy
) -> dict[str, Any]:
    """One decisions row, one feedback row and one ``decision.made`` event (FR-33, FR-54).

    Returns the verdict as graph state. Replays (status already past ``awaiting_approval``) return
    the stored verdict without writing again.
    """
    async with session_scope() as session:
        item = await _locked(session, item_id)
        if item.status != ItemStatus.AWAITING_APPROVAL:
            return await _replayed(session, item)
        option = _resolve_option(item, body)
        target = _TARGET[body.verdict]
        if decided_by == DecidedBy.AUTO and target == ItemStatus.APPROVED:
            target = ItemStatus.AUTO_APPROVED
        latency = _latency_ms(item.decision)
        transition(item, target)
        session.add(
            Decision(
                id=new_id(),
                tenant_id=item.tenant_id,
                item_id=item.id,
                verdict=body.verdict.value,
                option=option,
                edits=body.edits,
                decided_by=decided_by.value,
                latency_ms=latency,
            )
        )
        await session.flush()
        await record_decision_feedback(
            session, item=item, body=body, decided_by=decided_by, latency_ms=latency
        )
        if body.verdict == Verdict.SNOOZE and body.snooze_until is not None:
            await queue.enqueue(
                session,
                tenant_id=item.tenant_id,
                kind=JobKind.ACTION,
                item_id=item.id,
                payload={"op": UNSNOOZE_OP},
                run_at=_aware(body.snooze_until),
            )
        await emit(
            session,
            tenant_id=item.tenant_id,
            event="decision.made",
            item_id=item.id,
            extra={
                "verdict": body.verdict.value,
                "option": option,
                "decided_by": decided_by.value,
            },
        )
        return _verdict_json(body.verdict.value, option, body.edits, decided_by.value)


async def execute_actions(
    item_id: str, tenant_id: str, option_id: str | None, actions: list[dict[str, Any]], *, run: bool
) -> list[dict[str, Any]]:
    """``approved | auto_approved -> acting -> done`` in one transaction (FR-40, FR-41).

    ``run=False`` (autonomy ``suggest``) moves the item through without executing anything.
    ``action.done`` is emitted for every executed action, webhook included (C2).
    """
    done: list[dict[str, Any]] = []
    async with session_scope() as session:
        item = await _locked(session, item_id)
        if item.status in (ItemStatus.APPROVED, ItemStatus.AUTO_APPROVED):
            transition(item, ItemStatus.ACTING)
        elif item.status != ItemStatus.ACTING:
            return done
        ctx = ActionContext(session, uuid.UUID(tenant_id), item.id, option_id)
        for spec in actions if run else []:
            name = str(spec["type"])
            result = await run_action(ctx, name, dict(spec.get("params") or {}))
            await emit(
                session,
                tenant_id=item.tenant_id,
                event="action.done",
                item_id=item.id,
                extra={"action": name, "ok": result.ok},
            )
            done.append({"action": name, "ok": result.ok, "error": result.error})
        transition(item, ItemStatus.DONE)
    return done


async def complete_item(item_id: str) -> None:
    """``rejected | informational -> done``; anything else is left alone."""
    async with session_scope() as session:
        item = await _locked(session, item_id)
        if item.status in (ItemStatus.REJECTED, ItemStatus.INFORMATIONAL):
            transition(item, ItemStatus.DONE)


async def unsnooze(session: AsyncSession, item_id: str) -> bool:
    """``snoozed -> awaiting_approval`` in the caller's transaction; emits ``decision.ready``."""
    item = await _locked(session, item_id)
    if item.status != ItemStatus.SNOOZED:
        return False
    decision = dict(item.decision or {})
    decision["ready_at"] = utcnow().isoformat()
    item.decision = decision
    transition(item, ItemStatus.AWAITING_APPROVAL)
    await emit(session, tenant_id=item.tenant_id, event="decision.ready", item_id=item.id)
    return True
