"""Event emitter: enqueue a webhook fan-out job when someone subscribed (FR-42, contract C2).

Runs in the caller's transaction, so a rollback also discards the job.
"""

import uuid
from typing import Any, Literal, get_args

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.models import WebhookSubscription
from app.models.enums import JobKind
from app.workers import queue

EventName = Literal["item.triaged", "decision.ready", "decision.made", "action.done"]
EVENT_NAMES: frozenset[str] = frozenset(get_args(EventName))


async def emit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event: EventName,
    item_id: uuid.UUID,
    extra: dict[str, Any] | None = None,
) -> None:
    """Enqueue a fan-out job unless no enabled subscription lists `event`."""
    has_subscriber = await session.execute(
        select(
            exists().where(
                WebhookSubscription.tenant_id == tenant_id,
                WebhookSubscription.enabled.is_(True),
                WebhookSubscription.events.any(event),
            )
        )
    )
    if not has_subscriber.scalar():
        return
    await queue.enqueue(
        session,
        tenant_id=tenant_id,
        kind=JobKind.WEBHOOK,
        item_id=item_id,
        payload={
            "op": "fanout",
            "event": event,
            "event_id": f"evt_{new_id()}",
            "extra": extra or {},
        },
    )
