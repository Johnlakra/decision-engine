"""insert + enqueue -> worker -> item normalised, job done; failures retried (NFR-02, NFR-08)."""

from collections.abc import AsyncIterator, Mapping

import pytest
import pytest_asyncio
from sqlalchemy import select, text
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
from app.models.enums import ItemStatus, JobKind
from app.models.status import transition
from app.workers import queue
from app.workers.handlers import Handler
from app.workers.run import Worker
from tests.integration.graph_support import real_niches, runtime  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration


async def advance_stub(session: AsyncSession, job: Job) -> None:
    """Minimal PROCESS handler for queue-mechanics tests: new -> normalised, no LLM or graph."""
    item = await session.get(Item, job.item_id, with_for_update=True)
    assert item is not None
    transition(item, ItemStatus.NORMALISED)


STUB_HANDLERS = {JobKind.PROCESS: advance_stub}


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


def _worker(
    factory: async_sessionmaker[AsyncSession],
    *,
    manage_graph: bool = False,
    handlers: Mapping[JobKind, Handler] | None = None,
) -> Worker:
    return Worker(
        "test-worker",
        Settings(worker_batch_size=50),
        session_factory=factory,
        manage_graph=manage_graph,
        handlers=handlers,
    )


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
    await _worker(factory, handlers=STUB_HANDLERS).run_once()
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


async def _checkpoint_count(factory: async_sessionmaker[AsyncSession], thread_id: str) -> int:
    async with factory() as session:
        result = await session.execute(
            text("SELECT count(*) FROM checkpoints WHERE thread_id = :t"), {"t": thread_id}
        )
        return int(result.scalar_one())


async def _put_checkpoint(thread_id: str) -> None:
    from langgraph.checkpoint.base import empty_checkpoint

    from app.graph import run

    graph_runtime = await run._get_runtime()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    await graph_runtime.saver.aput(config, empty_checkpoint(), {"source": "input", "step": 0}, {})


async def _fail_terminally(
    factory: async_sessionmaker[AsyncSession], job: Job, boom: Handler
) -> None:
    async with factory() as session:
        row = await session.get(Job, job.id)
        assert row is not None
        row.attempts, row.max_attempts = 4, 5
        await session.commit()
    await _worker(factory, handlers={JobKind.PROCESS: boom}, manage_graph=True).run_once()


@pytest.mark.usefixtures("runtime")
async def test_terminal_failure_deletes_checkpoint_thread(  # NFR-03, NFR-07
    committed_db: async_sessionmaker[AsyncSession],
) -> None:
    async with committed_db() as session:
        tenant = Tenant(name="Thread Leak")
        session.add(tenant)
        await session.flush()
        item = Item(
            id=new_id(), tenant_id=tenant.id, source="manual", source_ref="leak", raw={"t": "x"}
        )
        session.add(item)
        await session.flush()
        job_id = await queue.enqueue(
            session, tenant_id=tenant.id, kind=JobKind.PROCESS, item_id=item.id
        )
        await session.commit()
        job = await session.get(Job, job_id)
    assert job is not None
    thread_id = str(item.id)
    await _put_checkpoint(thread_id)
    assert await _checkpoint_count(committed_db, thread_id) == 1

    async def boom(session: AsyncSession, claimed: Job) -> None:
        raise RuntimeError

    await _fail_terminally(committed_db, job, boom)

    fresh_item, fresh_job = await _reload(committed_db, item, job)
    assert (fresh_item.status, fresh_job.status) == ("failed", "failed")
    assert await _checkpoint_count(committed_db, thread_id) == 0


async def test_thread_delete_error_does_not_mask_failure(
    factory: async_sessionmaker[AsyncSession],
    seeded: tuple[Item, Job],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.graph import run

    async def broken_runtime() -> None:
        raise ConnectionError("checkpointer down")

    monkeypatch.setattr(run, "_get_runtime", broken_runtime)
    item, job = seeded

    async def boom(session: AsyncSession, claimed: Job) -> None:
        raise RuntimeError

    await _fail_terminally(factory, job, boom)
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert (fresh_item.status, fresh_job.status) == ("failed", "failed")
