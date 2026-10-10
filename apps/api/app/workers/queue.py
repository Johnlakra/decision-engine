"""Postgres job queue: SKIP LOCKED claims, leases, backoff retries (NFR-02, NFR-03)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.time import utcnow
from app.models.enums import JobKind, JobStatus
from app.models.job import Job

NOTIFY_CHANNEL = "jobs_new"
BACKOFF_BASE_S = 30
BACKOFF_CAP_S = 30 * 60
DEFAULT_LEASE = timedelta(minutes=5)
# PROCESS jobs run the whole graph inside one claim: chained nodes, each LLM call up to 45 s per
# provider attempt across a fallback chain. 15 min covers the worst case with margin, so a live
# job is not reclaimed (which would hit ItemBusy); a crashed worker is still recovered in 15 min.
PROCESS_LEASE = timedelta(minutes=15)
ITEM_BUSY_RETRY_DELAY = timedelta(seconds=15)
MAX_ERROR_CHARS = 200


@dataclass(frozen=True)
class QueueStats:
    depth: int
    oldest_age_s: float | None


def backoff_delay(attempts: int) -> timedelta:
    """30 s after the first failure, doubling, capped at 30 min."""
    exponent = max(attempts - 1, 0)
    return timedelta(seconds=min(BACKOFF_BASE_S * 2**exponent, BACKOFF_CAP_S))


def safe_error(error: str) -> str:
    """First line only, capped: errors must never carry item bodies."""
    lines = error.strip().splitlines()
    return (lines[0] if lines else "")[:MAX_ERROR_CHARS]


def describe_exception(exc: BaseException) -> str:
    """Class name only; exception messages may contain item content."""
    return type(exc).__name__


async def enqueue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    kind: JobKind,
    item_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    run_at: datetime | None = None,
    max_attempts: int = 5,
) -> uuid.UUID:
    """Add a job in the caller's transaction and wake listening workers on commit."""
    job = Job(
        id=new_id(),
        tenant_id=tenant_id,
        kind=kind.value,
        item_id=item_id,
        payload=payload or {},
        run_at=run_at or utcnow(),
        max_attempts=max_attempts,
        status=JobStatus.QUEUED.value,
        attempts=0,
    )
    session.add(job)
    await session.flush()
    await session.execute(
        text("SELECT pg_notify(:channel, :kind)"), {"channel": NOTIFY_CHANNEL, "kind": kind.value}
    )
    return job.id


async def claim(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int,
    kinds: Sequence[JobKind] | None = None,
) -> list[Job]:
    """Lock up to ``limit`` due jobs and mark them running. Caller must commit."""
    stmt = (
        select(Job)
        .where(Job.status == JobStatus.QUEUED.value, Job.run_at <= utcnow())
        .order_by(Job.run_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    if kinds:
        stmt = stmt.where(Job.kind.in_([k.value for k in kinds]))
    jobs = list((await session.scalars(stmt)).all())
    now = utcnow()
    for job in jobs:
        job.status = JobStatus.RUNNING.value
        job.locked_by = worker_id
        job.locked_at = now
        job.attempts += 1
    await session.flush()
    return jobs


async def complete(session: AsyncSession, job_id: uuid.UUID) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.DONE.value, locked_by=None, locked_at=None, last_error=None)
    )


async def fail(session: AsyncSession, job: Job, error: str) -> JobStatus:
    """Requeue with exponential backoff, or mark failed once attempts are exhausted."""
    exhausted = job.attempts >= job.max_attempts
    status = JobStatus.FAILED if exhausted else JobStatus.QUEUED
    values: dict[str, Any] = {
        "status": status.value,
        "locked_by": None,
        "locked_at": None,
        "last_error": safe_error(error),
    }
    if not exhausted:
        values["run_at"] = utcnow() + backoff_delay(job.attempts)
    await session.execute(update(Job).where(Job.id == job.id).values(**values))
    return status


async def release(session: AsyncSession, jobs: Sequence[Job]) -> None:
    """Give back claimed-but-unstarted jobs (graceful shutdown) without burning an attempt."""
    for job in jobs:
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status=JobStatus.QUEUED.value,
                locked_by=None,
                locked_at=None,
                attempts=max(job.attempts - 1, 0),
            )
        )


async def release_busy(session: AsyncSession, job: Job) -> None:
    """Requeue a job whose item is locked elsewhere, without burning an attempt."""
    await release(session, [job])
    await session.execute(
        update(Job).where(Job.id == job.id).values(run_at=utcnow() + ITEM_BUSY_RETRY_DELAY)
    )


async def reclaim_stale(session: AsyncSession, lease: timedelta | None = None) -> int:
    """Requeue running jobs whose lease expired (worker crashed); fail them if out of attempts.

    ``lease=None`` uses ``PROCESS_LEASE`` for process jobs and ``DEFAULT_LEASE`` for the rest; an
    explicit ``lease`` applies to every kind.
    """
    now = utcnow()
    process_lease = PROCESS_LEASE if lease is None else lease
    other_lease = DEFAULT_LEASE if lease is None else lease
    is_process = Job.kind == JobKind.PROCESS.value
    expired = or_(
        and_(is_process, Job.locked_at < now - process_lease),
        and_(~is_process, Job.locked_at < now - other_lease),
    )
    stale = Job.status == JobStatus.RUNNING.value, expired
    exhausted = (
        await session.execute(
            update(Job)
            .where(*stale, Job.attempts >= Job.max_attempts)
            .values(
                status=JobStatus.FAILED.value,
                locked_by=None,
                locked_at=None,
                last_error="LeaseExpired",
            )
            .returning(Job.id)
        )
    ).all()
    requeued = (
        await session.execute(
            update(Job)
            .where(*stale)
            .values(
                status=JobStatus.QUEUED.value,
                locked_by=None,
                locked_at=None,
                last_error="LeaseExpired",
            )
            .returning(Job.id)
        )
    ).all()
    return len(exhausted) + len(requeued)


async def queue_stats(session: AsyncSession) -> QueueStats:
    depth, oldest = (
        await session.execute(
            select(func.count(), func.min(Job.run_at)).where(Job.status == JobStatus.QUEUED.value)
        )
    ).one()
    age = max((utcnow() - oldest).total_seconds(), 0.0) if oldest else None
    return QueueStats(depth=int(depth), oldest_age_s=age)
