"""insert + enqueue -> worker -> item normalised, job done; failures retried (NFR-02, NFR-08)."""

import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
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

    async def broken_delete(_: object) -> None:
        raise ConnectionError("checkpointer down")

    monkeypatch.setattr(run, "delete_thread", broken_delete)
    item, job = seeded

    async def boom(session: AsyncSession, claimed: Job) -> None:
        raise RuntimeError

    await _fail_terminally(factory, job, boom)
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert (fresh_item.status, fresh_job.status) == ("failed", "failed")


async def _seed_item_job(
    factory: async_sessionmaker[AsyncSession],
    item: Item,
    kind: JobKind,
    *,
    status: str,
    payload: dict[str, object] | None = None,
    attempts: int = 4,
) -> uuid.UUID:
    async with factory() as session:
        row = await session.get(Item, item.id, with_for_update=True)
        assert row is not None
        row.status = status
        job_id = await queue.enqueue(
            session, tenant_id=item.tenant_id, kind=kind, item_id=item.id, payload=payload
        )
        job = await session.get(Job, job_id)
        assert job is not None
        job.attempts, job.max_attempts = attempts, 5
        await session.commit()
    return job_id


@pytest.mark.usefixtures("runtime")
async def test_failed_webhook_job_leaves_pending_approval_and_checkpoint(  # FR-33, NFR-03
    committed_db: async_sessionmaker[AsyncSession],
) -> None:
    """Terminal failure of a non-PROCESS job must not fail the item or drop its checkpoint."""
    async with committed_db() as session:
        tenant = Tenant(name="Webhook Fail")
        session.add(tenant)
        await session.flush()
        item = Item(
            id=new_id(), tenant_id=tenant.id, source="manual", source_ref="wh", raw={"t": "x"}
        )
        session.add(item)
        await session.commit()
    thread_id = str(item.id)
    await _put_checkpoint(thread_id)
    job_id = await _seed_item_job(committed_db, item, JobKind.WEBHOOK, status="awaiting_approval")
    # first claim must pick up only our job: drain others is unnecessary (kinds filtered by id)

    async def boom(session: AsyncSession, claimed: Job) -> None:
        raise RuntimeError

    await _worker(committed_db, handlers={JobKind.WEBHOOK: boom}, manage_graph=True).run_once()
    async with committed_db() as session:
        fresh_item = await session.get(Item, item.id)
        fresh_job = await session.get(Job, job_id)
    assert fresh_job is not None and fresh_item is not None
    assert fresh_job.status == "failed"
    assert fresh_item.status == "awaiting_approval"
    assert await _checkpoint_count(committed_db, thread_id) == 1


async def test_item_busy_releases_job_without_consuming_attempt(  # NFR-02, NFR-08
    factory: async_sessionmaker[AsyncSession], seeded: tuple[Item, Job]
) -> None:
    from app.graph.errors import ItemBusy

    item, job = seeded
    async with factory() as session:
        row = await session.get(Job, job.id)
        assert row is not None
        row.attempts, row.max_attempts = 4, 5  # one more burned attempt would fail it
        await session.commit()

    async def busy(session: AsyncSession, claimed: Job) -> None:
        raise ItemBusy("held elsewhere")

    await _worker(factory, handlers={JobKind.PROCESS: busy}).run_once()
    fresh_item, fresh_job = await _reload(factory, item, job)
    assert fresh_job.status == "queued"
    assert fresh_job.attempts == 4
    assert fresh_job.locked_by is None
    assert fresh_job.run_at > utcnow()
    assert fresh_item.status == "new"


async def test_process_job_gets_longer_lease_than_other_kinds(  # NFR-02
    factory: async_sessionmaker[AsyncSession], seeded: tuple[Item, Job]
) -> None:
    item, job = seeded
    async with factory() as session:
        other = await queue.enqueue(session, tenant_id=item.tenant_id, kind=JobKind.WEBHOOK)
        age = queue.DEFAULT_LEASE + timedelta(minutes=1)
        for job_id in (job.id, other):
            await session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status="running", locked_by="dead", locked_at=utcnow() - age, attempts=1)
            )
        assert await queue.reclaim_stale(session) == 1
        await session.commit()
        process_row = await session.get(Job, job.id)
        other_row = await session.get(Job, other)
    assert process_row is not None and other_row is not None
    assert process_row.status == "running"
    assert other_row.status == "queued"
