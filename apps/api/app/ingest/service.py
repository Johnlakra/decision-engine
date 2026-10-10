"""Ingest service: idempotent insert + `process` job in one transaction (FR-01, FR-06, FR-07)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.time import utcnow
from app.ingest.sensitivity import resolve_item_sensitivity
from app.models import Item
from app.models.enums import ItemStatus, JobKind
from app.schemas.ingest import IngestItemIn
from app.workers.queue import enqueue


def start_of_utc_day(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def seconds_until_utc_midnight(now: datetime) -> int:
    midnight = start_of_utc_day(now) + timedelta(days=1)
    return max(1, int((midnight - now.astimezone(UTC)).total_seconds()))


async def items_today(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Items created by this tenant since 00:00 UTC (one indexed count, ADR 0004)."""
    stmt = (
        select(func.count())
        .select_from(Item)
        .where(Item.tenant_id == tenant_id, Item.created_at >= start_of_utc_day(utcnow()))
    )
    return int((await session.execute(stmt)).scalar_one())


async def lock_tenant_quota(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Serialize count-and-insert per tenant until commit/rollback (NFR-05)."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"items-cap:{tenant_id}"},
    )


async def remaining_quota(session: AsyncSession, tenant_id: uuid.UUID, cap: int) -> int:
    return max(0, cap - await items_today(session, tenant_id))


async def daily_cap_reached(session: AsyncSession, tenant_id: uuid.UUID, cap: int) -> bool:
    return await items_today(session, tenant_id) >= cap


async def find_existing(
    session: AsyncSession, tenant_id: uuid.UUID, source: str, source_ref: str
) -> Item | None:
    """The stored item for (tenant, source, source_ref), if any (FR-07)."""
    stmt = select(Item).where(
        Item.tenant_id == tenant_id, Item.source == source, Item.source_ref == source_ref
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def ingest_one(
    session: AsyncSession, tenant_id: uuid.UUID, body: IngestItemIn
) -> tuple[Item, bool]:
    """Insert or find the item; on insert enqueue `process`. Caller commits.

    Returns ``(item, created)``; a repeat of (source, source_ref) returns the existing row.
    """
    values: dict[str, object] = {
        "id": new_id(),
        "tenant_id": tenant_id,
        "source": body.source,
        "source_ref": body.source_ref,
        "status": ItemStatus.NEW.value,
        "raw": body.payload,  # untouched (FR-06)
        "sensitivity": resolve_item_sensitivity(body.source, body.hints),
        "hints": body.hints.model_dump(exclude_none=True) if body.hints else None,
        "callback_url": body.callback_url,
    }
    if body.received_at is not None:
        values["received_at"] = body.received_at
    stmt = (
        pg_insert(Item)
        .values(**values)
        .on_conflict_do_nothing(index_elements=["tenant_id", "source", "source_ref"])
        .returning(Item.id)
    )
    inserted_id = (await session.execute(stmt)).scalar_one_or_none()
    if inserted_id is None:
        existing = (
            await session.execute(
                select(Item).where(
                    Item.tenant_id == tenant_id,
                    Item.source == body.source,
                    Item.source_ref == body.source_ref,
                )
            )
        ).scalar_one()
        return existing, False
    item = (
        await session.execute(
            select(Item).where(Item.id == inserted_id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    await enqueue(session, tenant_id=tenant_id, kind=JobKind.PROCESS, item_id=item.id)
    return item, True
