"""Atomic per-tenant daily counter for ``POST /v1/decide`` (code review M3; FR-35, NFR-05).

One decide call can cost several LLM calls and provider budgets are global, so each tenant
gets its own cap. Same store as the item cap (Postgres); one upsert is the whole check.
"""

import uuid

from sqlalchemy import Integer, literal
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.decide_usage import DecideUsage


async def try_consume_decide_call(session: AsyncSession, tenant_id: uuid.UUID, limit: int) -> bool:
    """Count one decide call; False (and no increment) once ``limit`` is reached today (UTC)."""
    if limit <= 0:
        return False
    insert_stmt = pg_insert(DecideUsage).values(
        tenant_id=tenant_id, day=utcnow().date(), calls=literal(1, Integer)
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[DecideUsage.tenant_id, DecideUsage.day],
        set_={"calls": DecideUsage.calls + 1},
        where=DecideUsage.calls < limit,
    )
    row = (await session.execute(upsert_stmt.returning(DecideUsage.calls))).first()
    await session.commit()
    return row is not None
