"""Pipeline stages run by the worker: normalise, triage (batched), then the graph (FR-20, NFR-03).

``prepare_batch`` is the C9 hook: it normalises every claimed ``new`` item and triages all
``normalised`` ones with ONE ``triage_items`` call, then commits. It never raises, because each
per-job ``process_item`` is idempotent by ``items.status`` and finishes the work alone.
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


class UnsupportedJob(RuntimeError):
    pass


async def _normalise_new(session: AsyncSession, items: Sequence[Item]) -> None:
    """Normalise each `new` item in its own savepoint; one bad item must not block the batch."""
    for item in items:
        if item.status != ItemStatus.NEW.value:
            continue
        try:
            async with session.begin_nested():
                await normalise_item(session, item)
        except Exception as exc:
            log.warning("normalise failed, left for the job handler", extra={"item_id": item.id})
            log.debug("normalise error %s", type(exc).__name__)


async def _prepare(factory: async_sessionmaker[AsyncSession], jobs: Sequence[Job]) -> None:
    item_ids = [
        job.item_id for job in jobs if job.kind == JobKind.PROCESS.value and job.item_id is not None
    ]
    if not item_ids:
        return
    async with factory() as session:
        items = list(
            await session.scalars(
                select(Item)
                .where(Item.id.in_(item_ids), Item.status.in_(_PREPARABLE))
                .order_by(Item.created_at)
                .with_for_update(skip_locked=True)
            )
        )
        await _normalise_new(session, items)
        ready = [item for item in items if item.status == ItemStatus.NORMALISED.value]
        if ready:
            await triage_service.triage_items(session, ready)
        await session.commit()


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
