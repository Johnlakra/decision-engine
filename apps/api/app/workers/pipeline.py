"""Pipeline stages run by the worker: normalise, triage (batched), then the graph (FR-20, NFR-03).

``prepare_batch`` is the C9 hook: it normalises every claimed ``new`` item (one short transaction
each) and triages the ``normalised`` ones in sub-batches of ``PREPARE_SUB_BATCH``, one
``triage_items`` call (one Laya call) per sub-batch. No row locks are held across LLM calls.
It never raises, because each per-job ``process_item`` is idempotent by ``items.status``
and finishes the work alone.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.models.enums import ItemStatus, JobKind
from app.models.item import Item
from app.models.job import Job
from app.normalise.service import normalise_item
from app.triage import service as triage_service

log = get_logger("app.workers.pipeline")

# The graph (and LangGraph with it) is imported at call time: see _run_graph.
RUNNABLE = frozenset({ItemStatus.TRIAGED.value, ItemStatus.DECIDING.value})
_PREPARABLE = (ItemStatus.NEW.value, ItemStatus.NORMALISED.value)
# One Laya call per sub-batch: bounds how long a triage transaction can stay open (NFR-03).
PREPARE_SUB_BATCH = 8


class UnsupportedJob(RuntimeError):
    pass


async def _load_detached(
    factory: async_sessionmaker[AsyncSession], item_ids: Sequence[uuid.UUID]
) -> list[Item]:
    """Read the preparable items WITHOUT row locks and detach them.

    The claimed jobs already give this worker exclusivity, so no ``FOR UPDATE`` is needed, and
    the connection goes back to the pool before any LLM call.
    """
    async with factory() as session:
        items = list(
            await session.scalars(
                select(Item)
                .where(Item.id.in_(item_ids), Item.status.in_(_PREPARABLE))
                .order_by(Item.created_at)
            )
        )
        session.expunge_all()
    return items


async def _normalise_one(factory: async_sessionmaker[AsyncSession], item: Item) -> None:
    """Normalise one detached item in its own short transaction; one bad item blocks no other."""
    try:
        async with factory() as session:
            session.add(item)
            await normalise_item(session, item)
            await session.commit()
            session.expunge(item)
    except Exception as exc:
        log.warning("normalise failed, left for the job handler", extra={"item_id": item.id})
        log.debug("normalise error %s", type(exc).__name__)


async def _triage_sub_batch(
    factory: async_sessionmaker[AsyncSession], items: Sequence[Item]
) -> None:
    async with factory() as session:
        for item in items:
            session.add(item)
        await triage_service.triage_items(session, items)
        await session.commit()
        session.expunge_all()


async def _prepare(factory: async_sessionmaker[AsyncSession], jobs: Sequence[Job]) -> None:
    item_ids = [
        job.item_id for job in jobs if job.kind == JobKind.PROCESS.value and job.item_id is not None
    ]
    if not item_ids:
        return
    items = await _load_detached(factory, item_ids)
    for item in items:
        if item.status == ItemStatus.NEW.value:
            await _normalise_one(factory, item)
    ready = [item for item in items if item.status == ItemStatus.NORMALISED.value]
    for start in range(0, len(ready), PREPARE_SUB_BATCH):
        await _triage_sub_batch(factory, ready[start : start + PREPARE_SUB_BATCH])


async def prepare_batch(factory: async_sessionmaker[AsyncSession], jobs: Sequence[Job]) -> None:
    """C9 hook, called once per claimed batch. Never raises."""
    try:
        await _prepare(factory, jobs)
    except Exception as exc:
        log.warning(
            "batch prepare failed; per-job handlers continue", extra={"error": repr(exc)[:80]}
        )


async def process_item(session: AsyncSession, job: Job) -> None:
    """Advance one item as far as the worker can: normalise, triage, then run the graph."""
    if job.item_id is None:
        raise UnsupportedJob("process job without item_id")
    item = await session.get(Item, job.item_id, with_for_update=True)
    if item is None:
        raise UnsupportedJob("item not found")
    if item.status == ItemStatus.NEW.value:
        await normalise_item(session, item)
    if item.status == ItemStatus.NORMALISED.value:
        await triage_service.triage_items(session, [item])
    status = item.status
    # Commit the status change now. The worker completes the job in a SEPARATE transaction
    # afterwards; a crash in between re-runs the job, which is safe because run_item is idempotent.
    await session.commit()  # run_item reads the item on its own connection
    if status in RUNNABLE:
        await run_graph(item.id)


async def run_graph(item_id: uuid.UUID) -> None:
    """Run the niche graph. LLM outages propagate so the job is retried (the item is not lost).

    ``run_item`` takes the item lock itself; do not wrap it in ``item_lock``.
    """
    from app.graph.run import run_item

    outcome = await run_item(item_id)
    log.info(
        "graph ran",
        extra={"item_id": item_id, "status": outcome.status, "wait": outcome.interrupted},
    )


async def unsnooze(item_id: uuid.UUID) -> None:
    from app.graph.run import unsnooze_item

    await unsnooze_item(item_id)
