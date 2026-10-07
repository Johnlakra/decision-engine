"""Job handlers keyed by JobKind. Phase 1 replaces the stubs with the real pipeline."""

from collections.abc import Awaitable, Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ItemStatus, JobKind
from app.models.item import Item
from app.models.job import Job
from app.models.status import transition

Handler = Callable[[AsyncSession, Job], Awaitable[None]]


class UnsupportedJob(RuntimeError):
    pass


async def handle_process(session: AsyncSession, job: Job) -> None:
    """Stub (Phase 0): normalisation arrives in 1.2; for now just advance the status."""
    if job.item_id is None:
        raise UnsupportedJob("process job without item_id")
    item = await session.get(Item, job.item_id, with_for_update=True)
    if item is None:
        raise UnsupportedJob("item not found")
    transition(item, ItemStatus.NORMALISED)


HANDLERS: Mapping[JobKind, Handler] = {JobKind.PROCESS: handle_process}
