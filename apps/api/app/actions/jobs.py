"""Action job handler: reminder_due emits action.done (C4, FR-41)."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.events import emit
from app.models import ActionLog, Job

log = logging.getLogger(__name__)


async def handle_action_job(session: AsyncSession, job: Job) -> None:
    payload = job.payload or {}
    if payload.get("op") != "reminder_due":
        log.warning("unknown action job op=%s", payload.get("op"))
        return
    row = await session.get(ActionLog, uuid.UUID(str(payload.get("action_log_id"))))
    if row is None:
        log.warning("reminder_due without action_log row job=%s", job.id)
        return
    await emit(
        session,
        tenant_id=row.tenant_id,
        event="action.done",
        item_id=row.item_id,
        extra={"action": row.action, "ok": True},
    )
