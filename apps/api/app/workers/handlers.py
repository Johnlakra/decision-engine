"""Job handlers keyed by JobKind (C9). Only process_item commits (run_item needs the rows)."""

from collections.abc import Awaitable, Callable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.jobs import handle_action_job
from app.connectors.poll import handle_poll
from app.integrations.webhooks_out import handle_webhook_job
from app.models.enums import JobKind
from app.models.job import Job
from app.workers import pipeline
from app.workers.pipeline import UnsupportedJob, process_item

Handler = Callable[[AsyncSession, Job], Awaitable[None]]

__all__ = ["HANDLERS", "Handler", "UnsupportedJob", "handle_action", "process_item"]

OP_UNSNOOZE = "unsnooze"


async def handle_action(session: AsyncSession, job: Job) -> None:
    """ACTION jobs: ``payload.op`` ``unsnooze`` -> graph; anything else -> actions.jobs."""
    if (job.payload or {}).get("op") == OP_UNSNOOZE:
        if job.item_id is None:
            raise UnsupportedJob("unsnooze job without item_id")
        await pipeline.unsnooze(job.item_id)
        return
    await handle_action_job(session, job)


HANDLERS: Mapping[JobKind, Handler] = {
    JobKind.PROCESS: process_item,
    JobKind.WEBHOOK: handle_webhook_job,
    JobKind.ACTION: handle_action,
    JobKind.POLL: handle_poll,
}
