"""Queue behaviour against real Postgres, including concurrent claimers (NFR-02, NFR-03)."""

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.time import utcnow
from app.models import Job, Tenant
from app.models.enums import JobKind, JobStatus
from app.workers import queue

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def committed_tenant(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[Tenant]:
    async with factory() as session:
        tenant = Tenant(name="Queue Test")
        session.add(tenant)
        await session.commit()
    yield tenant
    async with factory() as session:  # cascades to jobs
        await session.delete(await session.get(Tenant, tenant.id))
        await session.commit()


async def test_enqueue_sets_defaults(db_session: AsyncSession, tenant: Tenant) -> None:
    job_id = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    job = await db_session.get(Job, job_id)
    assert job is not None
    assert (job.status, job.attempts, job.max_attempts) == ("queued", 0, 5)


async def test_two_sessions_claim_disjoint_jobs(
    factory: async_sessionmaker[AsyncSession], committed_tenant: Tenant
) -> None:
    async with factory() as seed:
        ids = {
            await queue.enqueue(seed, tenant_id=committed_tenant.id, kind=JobKind.PROCESS)
            for _ in range(6)
        }
        await seed.commit()
    async with factory() as first, factory() as second:
        mine = await queue.claim(first, worker_id="a", limit=3)
        theirs = await queue.claim(second, worker_id="b", limit=3)  # first still holds its locks
        a, b = {j.id for j in mine}, {j.id for j in theirs}
        await first.commit()
        await second.commit()
    assert len(a) == 3 and len(b) == 3
    assert a.isdisjoint(b)
    assert a | b == ids
    assert all(j.status == "running" and j.attempts == 1 for j in mine + theirs)


async def test_claim_skips_future_jobs(db_session: AsyncSession, tenant: Tenant) -> None:
    await queue.enqueue(
        db_session, tenant_id=tenant.id, kind=JobKind.PROCESS, run_at=utcnow() + timedelta(hours=1)
    )
    claimed = await queue.claim(db_session, worker_id="w", limit=10, kinds=[JobKind.PROCESS])
    assert [j for j in claimed if j.tenant_id == tenant.id] == []


async def test_stale_lease_is_reclaimed(db_session: AsyncSession, tenant: Tenant) -> None:
    fresh = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    stale = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    now = utcnow()
    for job_id, locked in ((fresh, now), (stale, now - queue.PROCESS_LEASE - timedelta(minutes=1))):
        await db_session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status="running", locked_by="dead", locked_at=locked, attempts=1)
        )
    assert await queue.reclaim_stale(db_session) == 1
    rows = {
        j.id: j
        for j in (await db_session.scalars(select(Job).where(Job.tenant_id == tenant.id))).all()
    }
    await db_session.refresh(rows[stale])
    await db_session.refresh(rows[fresh])
    assert rows[stale].status == "queued" and rows[stale].locked_by is None
    assert rows[fresh].status == "running"


async def test_five_failures_end_in_failed_with_growing_backoff(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    job_id = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    delays: list[float] = []
    for attempt in range(1, 6):
        await db_session.execute(update(Job).where(Job.id == job_id).values(run_at=utcnow()))
        claimed = [
            j for j in await queue.claim(db_session, worker_id="w", limit=50) if j.id == job_id
        ]
        assert len(claimed) == 1 and claimed[0].attempts == attempt
        status = await queue.fail(db_session, claimed[0], "ValueError")
        await db_session.refresh(claimed[0])
        if attempt < 5:
            assert status is JobStatus.QUEUED
            delays.append((claimed[0].run_at - utcnow()).total_seconds())
    assert status is JobStatus.FAILED
    assert claimed[0].status == "failed"
    assert [round(d / 30) for d in delays] == [1, 2, 4, 8]


async def test_last_error_has_no_body(db_session: AsyncSession, tenant: Tenant) -> None:
    job_id = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    job = (await db_session.scalars(select(Job).where(Job.id == job_id))).one()
    job.attempts = 1
    await queue.fail(db_session, job, "Boom\n" + "private email body " * 100)
    await db_session.refresh(job)
    assert job.last_error == "Boom"


async def test_complete_marks_done(db_session: AsyncSession, tenant: Tenant) -> None:
    job_id = await queue.enqueue(db_session, tenant_id=tenant.id, kind=JobKind.PROCESS)
    await queue.complete(db_session, job_id)
    job = await db_session.get(Job, job_id)
    assert job is not None
    await db_session.refresh(job)
    assert job.status == "done"


async def test_queue_stats(db_session: AsyncSession, tenant: Tenant) -> None:
    before = await queue.queue_stats(db_session)
    await queue.enqueue(
        db_session,
        tenant_id=tenant.id,
        kind=JobKind.PROCESS,
        run_at=utcnow() - timedelta(seconds=90),
    )
    after = await queue.queue_stats(db_session)
    assert after.depth == before.depth + 1
    assert after.oldest_age_s is not None and after.oldest_age_s >= 89
