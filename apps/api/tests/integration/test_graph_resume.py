"""The runner over the real Postgres checkpointer (FR-30, FR-33, FR-34, FR-54, NFR-03)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graph import locks, run
from app.graph.errors import InvalidDecision, ItemBusy, ItemNotFound, NotAwaitingApproval
from app.llm import gateway
from app.llm.errors import LLMUnavailable, NoPrivateProvider
from app.models import ActionLog, Decision, Feedback, Job, Tenant
from app.models.enums import JobKind
from app.schemas.decision import DecisionIn
from tests.fakes.fake_llm import FakeLLM, fake_llm  # noqa: F401
from tests.integration.graph_support import (
    DECISION_OUT,
    count_rows,
    event_names,
    load,
    make_item,
    real_niches,  # noqa: F401
    runtime,  # noqa: F401
)

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


def approve(**kw: object) -> DecisionIn:
    return DecisionIn(verdict="approve", **kw)  # type: ignore[arg-type]


async def checkpoint_rows(factory: SessionFactory, item_id: uuid.UUID) -> int:
    async with factory() as session:
        stmt = text("SELECT count(*) FROM checkpoints WHERE thread_id = :t")
        return int((await session.execute(stmt, {"t": str(item_id)})).scalar_one())


def script(llm: FakeLLM) -> FakeLLM:
    return llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)


@pytest.mark.usefixtures("runtime")
async def test_run_waits_for_approval_and_resume_finishes(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)

    first = await run.run_item(item_id)

    assert (first.status, first.interrupted) == ("awaiting_approval", True)
    assert await checkpoint_rows(committed_db, item_id) > 0
    assert await event_names(committed_db) == ["decision.ready"]

    outcome = await run.resume_item(item_id, tenant_committed.id, approve())

    assert (outcome.status, outcome.interrupted) == ("done", False)
    assert await checkpoint_rows(committed_db, item_id) == 0  # deleted at END only
    assert len(fake_llm.calls_for("decide")) == 1  # resume did not re-decide
    assert await count_rows(committed_db, Decision) == 1
    assert await count_rows(committed_db, Feedback) == 1
    assert await count_rows(committed_db, ActionLog) == 1
    assert await event_names(committed_db) == [
        "action.done",
        "decision.made",
        "decision.ready",
    ]


@pytest.mark.usefixtures("runtime")
async def test_run_item_twice_is_a_noop_when_waiting(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)

    again = await run.run_item(item_id)

    assert again.interrupted and len(fake_llm.calls_for("decide")) == 1
    assert await event_names(committed_db) == ["decision.ready"]


@pytest.mark.usefixtures("runtime")
async def test_reject_ends_done_without_actions(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)

    outcome = await run.resume_item(
        item_id, tenant_committed.id, DecisionIn(verdict="reject", note="no")
    )

    assert outcome.status == "done"
    assert await count_rows(committed_db, ActionLog) == 0
    assert await count_rows(committed_db, Decision) == 1
    assert await count_rows(committed_db, Feedback) == 1


@pytest.mark.usefixtures("runtime")
async def test_second_resume_is_not_awaiting(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)
    await run.resume_item(item_id, tenant_committed.id, approve())

    with pytest.raises(NotAwaitingApproval):
        await run.resume_item(item_id, tenant_committed.id, approve())

    assert await count_rows(committed_db, Decision) == 1


@pytest.mark.usefixtures("runtime")
async def test_busy_item_raises_item_busy(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)

    async with locks.item_lock(item_id):
        with pytest.raises(ItemBusy):
            await run.resume_item(item_id, tenant_committed.id, approve())
    outcome = await run.resume_item(item_id, tenant_committed.id, approve())  # lock released
    assert outcome.status == "done"


@pytest.mark.usefixtures("runtime")
async def test_invalid_option_and_foreign_tenant_leave_the_thread_waiting(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)

    with pytest.raises(InvalidDecision):
        await run.resume_item(item_id, tenant_committed.id, approve(option="E"))
    with pytest.raises(ItemNotFound):
        await run.resume_item(item_id, uuid.uuid4(), approve())
    with pytest.raises(ItemNotFound):
        await run.resume_item(uuid.uuid4(), tenant_committed.id, approve())

    assert (await load(committed_db, item_id)).status == "awaiting_approval"
    assert (await run.resume_item(item_id, tenant_committed.id, approve())).status == "done"


@pytest.mark.usefixtures("runtime")
async def test_snooze_then_unsnooze_waits_again(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    script(fake_llm)
    await run.run_item(item_id)
    until = datetime.now(UTC) + timedelta(hours=2)

    snoozed = await run.resume_item(
        item_id, tenant_committed.id, DecisionIn(verdict="snooze", snooze_until=until)
    )

    assert (snoozed.status, snoozed.interrupted) == ("snoozed", True)
    async with committed_db() as session:
        jobs = (await session.scalars(select(Job).where(Job.kind == JobKind.ACTION.value))).all()
    assert [j.payload["op"] for j in jobs] == ["unsnooze"]
    with pytest.raises(NotAwaitingApproval):
        await run.resume_item(item_id, tenant_committed.id, approve())

    await run.unsnooze_item(item_id)

    assert (await load(committed_db, item_id)).status == "awaiting_approval"
    assert (await event_names(committed_db)).count("decision.ready") == 2
    final = await run.resume_item(item_id, tenant_committed.id, approve())
    assert final.status == "done"
    assert await count_rows(committed_db, Decision) == 2  # snooze + approve
    assert len(fake_llm.calls_for("decide")) == 1


@pytest.mark.usefixtures("runtime")
async def test_llm_unavailable_leaves_item_deciding_and_retry_continues(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed)
    fake_llm.script("normalise", {"entities": {}}, repeat=True)
    fake_llm.script("decide", LLMUnavailable("down"), DECISION_OUT)

    with pytest.raises(LLMUnavailable):
        await run.run_item(item_id)
    assert (await load(committed_db, item_id)).status == "deciding"

    outcome = await run.run_item(item_id)

    assert (outcome.status, outcome.interrupted) == ("awaiting_approval", True)
    assert len(fake_llm.calls_for("decide")) == 2


@pytest.mark.usefixtures("runtime")
async def test_private_item_without_private_provider_stays_deciding(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed, sensitivity="private")
    fake_llm.private_available = False
    script(fake_llm)

    with pytest.raises(NoPrivateProvider):
        await run.run_item(item_id)

    assert (await load(committed_db, item_id)).status == "deciding"
    assert await count_rows(committed_db, Decision) == 0


class Crash(BaseException):  # noqa: N818 - escapes every `except Exception`
    pass


@pytest.mark.usefixtures("runtime")
async def test_crash_mid_graph_resumes_without_rerunning_extract(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await make_item(committed_db, tenant_committed, niche="tech_stack")
    fake_llm.script("normalise", {"entities": {"project_type": "web_app"}}, repeat=True)
    fake_llm.script("decide", DECISION_OUT)
    scripted = gateway.complete_json
    crashed: list[bool] = []

    async def crash_once(purpose: str, *args: Any, **kwargs: Any) -> Any:
        if purpose == "decide" and not crashed:
            crashed.append(True)
            raise Crash
        return await scripted(purpose, *args, **kwargs)

    monkeypatch.setattr(gateway, "complete_json", crash_once)

    with pytest.raises(Crash):
        await run.run_item(item_id)
    outcome = await run.run_item(item_id)

    assert outcome.status == "awaiting_approval"
    assert len(fake_llm.calls_for("normalise")) == 1  # extract ran exactly once
    assert await event_names(committed_db) == ["decision.ready"]


@pytest.mark.usefixtures("runtime")
async def test_informational_item_finishes_and_thread_is_deleted(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    informational = {
        "mode": "on",
        "decided_by": "laya",
        "answers": {
            "needs_decision": {
                "type": "choice",
                "choice": "B",
                "confidence": 0.99,
                "source": "laya",
            },
        },
        "questions": {},
        "latency_ms": 1,
    }
    item_id = await make_item(committed_db, tenant_committed, triage=informational)

    outcome = await run.run_item(item_id)

    assert (outcome.status, outcome.interrupted) == ("done", False)
    assert await checkpoint_rows(committed_db, item_id) == 0
    assert fake_llm.calls == []


@pytest.mark.usefixtures("runtime")
async def test_run_item_ignores_items_not_ready(
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await make_item(committed_db, tenant_committed, status="done")

    outcome = await run.run_item(item_id)

    assert (outcome.status, outcome.interrupted) == ("done", False)
    assert fake_llm.calls == []
