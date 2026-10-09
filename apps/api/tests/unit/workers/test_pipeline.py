"""Worker pipeline wiring on real Postgres (FR-20, NFR-02, NFR-03). C9 batch hook + handlers."""

import uuid
from collections.abc import AsyncIterator, Sequence
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
from app.models import Item, Job, Tenant
from app.models.enums import JobKind
from app.triage import service as triage_service
from app.workers import handlers, pipeline, queue
from app.workers.run import Worker
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import FakeLLM

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
async def tenant_id(factory: Factory) -> AsyncIterator[uuid.UUID]:
    async with factory() as session:
        row = Tenant(name="Pipeline")
        session.add(row)
        await session.commit()
    yield row.id
    async with factory() as session:
        await session.delete(await session.get(Tenant, row.id))
        await session.commit()


async def _seed(
    factory: Factory, tenant_id: uuid.UUID, count: int, status: str = "new"
) -> list[tuple[uuid.UUID, uuid.UUID]]:
    pairs = []
    async with factory() as session:
        for index in range(count):
            item = Item(
                id=new_id(),
                tenant_id=tenant_id,
                source="manual",
                source_ref=f"pipe-{index}-{new_id()}",
                raw={"text": f"Invoice {index} is overdue"},
                hints={"title": f"Invoice {index}", "body": "please pay", "language": "en"},
                status=status,
                content={"title": f"Invoice {index}", "body": "x"} if status != "new" else None,
            )
            session.add(item)
            await session.flush()
            job_id = await queue.enqueue(
                session, tenant_id=tenant_id, kind=JobKind.PROCESS, item_id=item.id
            )
            pairs.append((item.id, job_id))
        await session.commit()
    return pairs


async def _status(factory: Factory, item_id: uuid.UUID) -> str:
    async with factory() as session:
        return (await session.scalars(select(Item).where(Item.id == item_id))).one().status


async def _jobs(factory: Factory, job_ids: Sequence[uuid.UUID]) -> list[Job]:
    async with factory() as session:
        return list(await session.scalars(select(Job).where(Job.id.in_(job_ids))))


async def test_claimed_batch_of_five_makes_one_laya_call(
    factory: Factory,
    tenant_id: uuid.UUID,
    fake_llm: FakeLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-20: the prepare hook normalises 5 new items and triages them in one Laya batch."""
    laya = FakeLayaClient()
    monkeypatch.setattr(triage_service, "get_laya_client", lambda: laya)
    pairs = await _seed(factory, tenant_id, 5)
    jobs = await _jobs(factory, [job_id for _, job_id in pairs])

    await pipeline.prepare_batch(factory, jobs)

    core_calls = [call for call in laya.calls if len(call["states"]) == 5]
    assert len(core_calls) == 1
    for item_id, _ in pairs:
        assert await _status(factory, item_id) != "new"


async def test_prepare_failure_does_not_stop_per_job_handlers(
    factory: Factory, tenant_id: uuid.UUID
) -> None:
    """NFR-02: a raising prepare hook is logged and every job still completes."""
    pairs = await _seed(factory, tenant_id, 3)

    async def broken(_: Factory, __: Sequence[Job]) -> None:
        raise RuntimeError("hook down")

    seen: list[uuid.UUID] = []

    async def handler(session: AsyncSession, job: Job) -> None:
        assert job.item_id is not None
        seen.append(job.item_id)

    worker = Worker(
        "t",
        Settings(worker_batch_size=10),
        session_factory=factory,
        handlers={JobKind.PROCESS: handler},
        prepare=broken,
        manage_graph=False,
    )
    await worker.run_once()
    assert {item_id for item_id, _ in pairs} <= set(seen)
    done = await _jobs(factory, [job_id for _, job_id in pairs])
    assert {job.status for job in done} == {"done"}


async def test_prepare_batch_swallows_triage_errors(
    factory: Factory, tenant_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("triage exploded")

    monkeypatch.setattr(triage_service, "triage_items", boom)
    pairs = await _seed(factory, tenant_id, 2)
    jobs = await _jobs(factory, [job_id for _, job_id in pairs])
    await pipeline.prepare_batch(factory, jobs)  # must not raise
    assert {await _status(factory, item_id) for item_id, _ in pairs} == {"new"}


async def test_process_job_for_awaiting_approval_is_a_noop(
    factory: Factory, tenant_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The graph already waits for a human: no normalise, no triage, no run."""
    ((item_id, job_id),) = await _seed(factory, tenant_id, 1, status="awaiting_approval")
    calls: list[str] = []

    async def fake_run(_: uuid.UUID) -> None:
        calls.append("run")

    async def fake_triage(*_: Any, **__: Any) -> list[Any]:
        calls.append("triage")
        return []

    monkeypatch.setattr(pipeline, "run_graph", fake_run)
    monkeypatch.setattr(triage_service, "triage_items", fake_triage)
    async with factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        await pipeline.process_item(session, job)
    assert calls == []
    assert await _status(factory, item_id) == "awaiting_approval"


async def test_process_item_runs_graph_for_triaged_item(
    factory: Factory, tenant_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    ((item_id, job_id),) = await _seed(factory, tenant_id, 1, status="triaged")
    ran: list[uuid.UUID] = []

    async def fake_run(item: uuid.UUID) -> None:
        ran.append(item)

    monkeypatch.setattr(pipeline, "run_graph", fake_run)
    async with factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        await pipeline.process_item(session, job)
    assert ran == [item_id]


async def test_process_item_propagates_graph_errors_for_retry(
    factory: Factory, tenant_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-03: an LLM outage fails the job (retried); the item stays deciding, never lost."""
    ((item_id, job_id),) = await _seed(factory, tenant_id, 1, status="deciding")

    async def down(_: uuid.UUID) -> None:
        raise RuntimeError("LLMUnavailable")

    monkeypatch.setattr(pipeline, "run_graph", down)
    worker = Worker(
        "t", Settings(worker_batch_size=10), session_factory=factory, manage_graph=False
    )
    await worker.run_once()
    (job,) = await _jobs(factory, [job_id])
    assert job.status == "queued" and job.last_error == "RuntimeError"
    assert await _status(factory, item_id) == "deciding"


def test_handler_map_covers_all_job_kinds() -> None:
    assert set(handlers.HANDLERS) == {JobKind.PROCESS, JobKind.WEBHOOK, JobKind.ACTION}
    assert handlers.HANDLERS[JobKind.PROCESS] is pipeline.process_item


async def test_action_dispatch_routes_unsnooze_and_reminder(
    db_session: AsyncSession, tenant: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsnoozed: list[uuid.UUID] = []
    reminded: list[Job] = []

    async def fake_unsnooze(item_id: uuid.UUID) -> None:
        unsnoozed.append(item_id)

    async def fake_reminder(_: AsyncSession, job: Job) -> None:
        reminded.append(job)

    monkeypatch.setattr(pipeline, "unsnooze", fake_unsnooze)
    monkeypatch.setattr(handlers, "handle_action_job", fake_reminder)
    item_id = new_id()
    unsnooze_job = Job(
        tenant_id=tenant.id, kind="action", item_id=item_id, payload={"op": "unsnooze"}
    )
    reminder_job = Job(
        tenant_id=tenant.id, kind="action", item_id=item_id, payload={"op": "reminder_due"}
    )
    await handlers.HANDLERS[JobKind.ACTION](db_session, unsnooze_job)
    await handlers.HANDLERS[JobKind.ACTION](db_session, reminder_job)
    assert unsnoozed == [item_id]
    assert reminded == [reminder_job]


async def test_process_item_without_item_id_raises(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    job = Job(tenant_id=tenant.id, kind="process", item_id=None)
    with pytest.raises(pipeline.UnsupportedJob, match="item_id"):
        await pipeline.process_item(db_session, job)


async def test_process_item_with_missing_item_raises(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    job = Job(tenant_id=tenant.id, kind="process", item_id=new_id())
    with pytest.raises(pipeline.UnsupportedJob, match="not found"):
        await pipeline.process_item(db_session, job)


async def test_run_forever_opens_and_closes_graph_runtime(
    factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-03: the checkpointer pool is opened at start and closed on stop."""
    from app.graph import run as graph_run

    events: list[str] = []

    async def opened() -> None:
        events.append("open")

    async def closed() -> None:
        events.append("close")

    monkeypatch.setattr(graph_run, "open_runtime", opened)
    monkeypatch.setattr(graph_run, "close_runtime", closed)
    worker = Worker("t", Settings(worker_batch_size=1), session_factory=factory)
    worker.stop()
    await worker.run_forever()
    assert events == ["open", "close"]
