"""Worker lifecycle on real Postgres: SIGTERM, LISTEN wake, crash-resume (NFR-02, NFR-03)."""

import asyncio
import os
import signal
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

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
from app.workers.handlers import HANDLERS, UnsupportedJob, handle_process
from app.workers.run import Worker

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


@pytest_asyncio.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def factory(engine: AsyncEngine) -> Factory:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def tenant_id(factory: Factory) -> AsyncIterator[Any]:
    async with factory() as session:
        row = Tenant(name="Lifecycle")
        session.add(row)
        await session.commit()
    yield row.id
    async with factory() as session:
        await session.delete(await session.get(Tenant, row.id))
        await session.commit()


async def _add_items(factory: Factory, tenant_id: Any, count: int) -> list[tuple[Any, Any]]:
    """Insert `count` items, each with a queued process job. Returns (item_id, job_id) pairs."""
    pairs = []
    async with factory() as session:
        for index in range(count):
            item = Item(
                id=new_id(), tenant_id=tenant_id, source="manual",
                source_ref=f"life-{index}-{new_id()}", raw={"n": index},
            )  # fmt: skip
            session.add(item)
            await session.flush()
            job_id = await queue.enqueue(
                session, tenant_id=tenant_id, kind=JobKind.PROCESS, item_id=item.id,
                run_at=utcnow() - timedelta(seconds=count - index),
            )  # fmt: skip
            pairs.append((item.id, job_id))
        await session.commit()
    return pairs


async def _state(factory: Factory, item_id: Any, job_id: Any) -> tuple[str, str, int]:
    async with factory() as session:
        item = (await session.scalars(select(Item).where(Item.id == item_id))).one()
        job = (await session.scalars(select(Job).where(Job.id == job_id))).one()
    return item.status, job.status, job.attempts


def _worker(factory: Factory, database_url: str, **kwargs: Any) -> Worker:
    settings = Settings(_env_file=None, database_url=database_url, worker_batch_size=10)  # type: ignore[arg-type]
    return Worker("life-worker", settings, session_factory=factory, **kwargs)


async def test_sigterm_finishes_current_job_and_releases_the_rest(
    factory: Factory, tenant_id: Any, migrated_db: str
) -> None:
    """Graceful stop: the in-flight job completes, unstarted ones return to the queue."""
    (first_item, first_job), (second_item, second_job) = await _add_items(factory, tenant_id, 2)
    worker = _worker(factory, migrated_db)
    started = asyncio.Event()

    async def handler(session: AsyncSession, job: Job) -> None:
        started.set()
        os.kill(os.getpid(), signal.SIGTERM)  # arrives while this job is mid-flight
        await asyncio.sleep(0.2)  # the loop gets the signal during this await
        await handle_process(session, job)

    worker._handlers = {JobKind.PROCESS: handler}
    await asyncio.wait_for(worker.run_forever(), timeout=15)

    assert started.is_set()
    assert await _state(factory, first_item, first_job) == ("normalised", "done", 1)
    # released without burning an attempt, so it is picked up by the next worker
    assert await _state(factory, second_item, second_job) == ("new", "queued", 0)


async def test_stop_before_any_job_leaves_queue_untouched(
    factory: Factory, tenant_id: Any, migrated_db: str
) -> None:
    ((item_id, job_id),) = await _add_items(factory, tenant_id, 1)
    worker = _worker(factory, migrated_db)
    worker.stop()
    await asyncio.wait_for(worker.run_forever(), timeout=5)
    assert await _state(factory, item_id, job_id) == ("new", "queued", 0)


async def test_run_forever_processes_jobs_when_listen_is_unavailable(
    factory: Factory, tenant_id: Any
) -> None:
    """LISTEN failure (unreachable DSN) falls back to polling and still drains the queue."""
    ((item_id, job_id),) = await _add_items(factory, tenant_id, 1)
    worker = _worker(factory, "postgresql+asyncpg://nobody:x@127.0.0.1:1/none")
    task = asyncio.create_task(worker.run_forever())
    try:
        for _ in range(50):
            if (await _state(factory, item_id, job_id))[1] == "done":
                break
            await asyncio.sleep(0.1)
    finally:
        worker.stop()
        await asyncio.wait_for(task, timeout=10)
    assert await _state(factory, item_id, job_id) == ("normalised", "done", 1)


async def test_notify_wakes_an_idle_worker_before_the_poll_interval(
    factory: Factory, tenant_id: Any, migrated_db: str
) -> None:
    """With LISTEN working, a new job is picked up long before the idle poll delay expires."""
    worker = _worker(factory, migrated_db)
    worker.settings = Settings(
        _env_file=None,
        database_url=migrated_db,
        worker_idle_poll_seconds=60,
        worker_batch_size=10,  # type: ignore[arg-type]
    )
    task = asyncio.create_task(worker.run_forever())
    try:
        await asyncio.sleep(3.6)  # idle polls at 1 s and 2 s are done; the next sleep is 4 s
        ((item_id, job_id),) = await _add_items(factory, tenant_id, 1)
        for _ in range(25):  # 2.5 s, well inside the 4 s sleep, so only NOTIFY can explain it
            if (await _state(factory, item_id, job_id))[1] == "done":
                break
            await asyncio.sleep(0.1)
    finally:
        worker.stop()
        await asyncio.wait_for(task, timeout=10)
    assert (await _state(factory, item_id, job_id))[1] == "done"


async def test_crashed_worker_job_is_reclaimed_and_finished_by_next_worker(
    factory: Factory, tenant_id: Any, migrated_db: str
) -> None:
    ((item_id, job_id),) = await _add_items(factory, tenant_id, 1)
    async with factory() as session:  # worker A claims and dies without finishing
        await queue.claim(session, worker_id="dead", limit=1)
        await session.commit()
    assert (await _state(factory, item_id, job_id))[1] == "running"
    async with factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.locked_at = utcnow() - timedelta(minutes=10)
        await session.commit()
    worker = _worker(factory, migrated_db, handlers=HANDLERS)
    await worker._maybe_reclaim()
    await worker.run_once()
    assert await _state(factory, item_id, job_id) == ("normalised", "done", 2)


async def test_unknown_job_kind_is_failed_with_backoff_not_dropped(
    factory: Factory, tenant_id: Any, migrated_db: str
) -> None:
    ((item_id, job_id),) = await _add_items(factory, tenant_id, 1)
    await _worker(factory, migrated_db, handlers={}).run_once()
    async with factory() as session:
        job = (await session.scalars(select(Job).where(Job.id == job_id))).one()
    assert job.status == "queued" and job.last_error == "UnsupportedJob"
    assert job.run_at > utcnow()
    assert (await _state(factory, item_id, job_id))[0] == "new"


# --- handle_process contract ---


async def test_handle_process_without_item_id_raises(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    job = Job(tenant_id=tenant.id, kind="process", item_id=None)
    with pytest.raises(UnsupportedJob, match="item_id"):
        await handle_process(db_session, job)


async def test_handle_process_with_missing_item_raises(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    job = Job(tenant_id=tenant.id, kind="process", item_id=new_id())
    with pytest.raises(UnsupportedJob, match="not found"):
        await handle_process(db_session, job)


async def test_handle_process_moves_new_item_to_normalised(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    item = Item(id=new_id(), tenant_id=tenant.id, source="manual", source_ref="hp-1", raw={})
    db_session.add(item)
    await db_session.flush()
    await handle_process(db_session, Job(tenant_id=tenant.id, kind="process", item_id=item.id))
    assert item.status == "normalised"
