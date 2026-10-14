"""Enqueue ``poll`` jobs for feed sources that are due (FR-90, docs/CONNECTORS.md).

Run every few minutes from cron or a compose service: ``python -m app.connectors.schedule``.
A source is due when it has never been polled or its last poll is older than ``POLL_INTERVAL``.
A source with a queued or running poll job is skipped, so repeated runs never stack jobs.
"""

import asyncio
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.feed_urls import FEED_TYPES
from app.connectors.poll import POLL_INTERVAL, POLL_SOURCE_KEY
from app.core.time import utcnow
from app.db.session import session_scope
from app.models.enums import JobKind, JobStatus
from app.models.job import Job
from app.models.source import Source
from app.workers.queue import enqueue

OPEN_JOB_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)


async def _due_sources(session: AsyncSession, now: datetime) -> Sequence[Source]:
    cutoff = now - POLL_INTERVAL
    stmt = select(Source).where(
        Source.enabled.is_(True),
        Source.type.in_(sorted(FEED_TYPES)),
        or_(Source.last_polled_at.is_(None), Source.last_polled_at <= cutoff),
    )
    return (await session.execute(stmt)).scalars().all()


async def _has_open_poll(session: AsyncSession, source: Source) -> bool:
    stmt = (
        select(Job.id)
        .where(
            Job.tenant_id == source.tenant_id,
            Job.kind == JobKind.POLL.value,
            Job.status.in_(OPEN_JOB_STATUSES),
            Job.payload[POLL_SOURCE_KEY].astext == str(source.id),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


async def enqueue_due_polls(session: AsyncSession, now: datetime | None = None) -> int:
    """Add one poll job per due source. Caller commits. Returns the number enqueued."""
    current = now or utcnow()
    enqueued = 0
    for source in await _due_sources(session, current):
        if await _has_open_poll(session, source):
            continue
        await enqueue(
            session,
            tenant_id=source.tenant_id,
            kind=JobKind.POLL,
            payload={POLL_SOURCE_KEY: str(source.id)},
        )
        enqueued += 1
    return enqueued


async def run() -> int:
    async with session_scope() as session:
        return await enqueue_due_polls(session)


def main() -> int:
    enqueued = asyncio.run(run())
    print(f"poll jobs enqueued: {enqueued}")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
