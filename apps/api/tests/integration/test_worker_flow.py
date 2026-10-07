"""insert + enqueue -> worker -> item normalised, job done; failures retried (NFR-02, NFR-08)."""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings
from app.core.ids import new_id
from app.core.time import utcnow
from app.models import Item, Job, Tenant
from app.models.enums import JobKind
from app.workers import queue
from app.workers.handlers import HANDLERS
from app.workers.run import Worker

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
async def seeded(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[tuple[Item, Job]]:
    async with factory() as session:
        tenant = Tenant(name="Worker Flow")
        session.add(tenant)
        await session.flush()
        item = Item(
            id=new_id(), tenant_id=tenant.id, source="manual", source_ref="flow-1", raw={"t": "x"}
        )
        session.add(item)
        await session.flush()
        job_id = await queue.enqueue(
            session, tenant_id=tenant.id, kind=JobKind.PROCESS, item_id=item.id
        )
        await session.commit()
        job = await session.get(Job, job_id)
    assert job is not None
    yield item, job
    async with factory() as session:
        await session.delete(await session.get(Tenant, tenant.id))
        await session.commit()


def _worker(factory: async_sessionmaker[AsyncSession], **kwargs: object) -> Worker:
    return Worker("test-worker", Settings(worker_batch_size=50), session_factory=factory, **kwargs)  # type: ignore[arg-type]


async def _reload(
    factory: async_sessionmaker[AsyncSession], item: Item, job: Job
) -> tuple[Item, Job]:
    async with factory() as session:
        fresh_item = (await session.scalars(select(Item).where(Item.id == item.id))).one()
        fresh_job = (await session.scalars(select(Job).where(Job.id == job.id))).one()
    return fresh_item, fresh_job


async def test_one_iteration_normalises_item_and_completes_job(
    factory: async_sessionmaker[AsyncSession], seeded: tuple[Item, Job]
) -> None:
    item, job = seeded
    await _worker(factory, handlers=HANDLERS).run_once()
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert fresh_item.status == "normalised"
    assert fresh_job.status == "done"
    assert fresh_job.attempts == 1


async def test_handler_exception_requeues_with_backoff_and_item_unchanged(
    factory: async_sessionmaker[AsyncSession], seeded: tuple[Item, Job]
) -> None:
    item, job = seeded

    async def boom(session: AsyncSession, claimed: Job) -> None:
        item_row = await session.get(Item, claimed.item_id)
        assert item_row is not None
        item_row.status = "normalised"  # must be rolled back with the failure
        raise RuntimeError("private body text")

    await _worker(factory, handlers={JobKind.PROCESS: boom}).run_once()
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert fresh_item.status == "new"
    assert fresh_job.status == "queued"
    assert fresh_job.last_error == "RuntimeError"
    assert (fresh_job.run_at - utcnow()).total_seconds() > 20


async def test_final_failure_marks_job_and_item_failed(
    factory: async_sessionmaker[AsyncSession], seeded: tuple[Item, Job]
) -> None:
    item, job = seeded
    async with factory() as session:
        row = await session.get(Job, job.id)
        assert row is not None
        row.attempts, row.max_attempts = 4, 5
        await session.commit()

    async def boom(session: AsyncSession, claimed: Job) -> None:
        raise RuntimeError

    await _worker(factory, handlers={JobKind.PROCESS: boom}).run_once()
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert fresh_job.status == "failed"
    assert fresh_item.status == "failed"
