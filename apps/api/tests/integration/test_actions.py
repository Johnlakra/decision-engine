"""run_action against real Postgres: idempotency through actions_log (FR-40, FR-41, NFR-07)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import actions  # noqa: F401
from app.actions.jobs import handle_action_job
from app.actions.registry import ActionContext, run_action
from app.core.ids import new_id
from app.models import ActionLog, Item, Job, Tenant, WebhookSubscription
from app.models.enums import JobKind

pytestmark = pytest.mark.integration


async def _ctx(session: AsyncSession, tenant: Tenant) -> ActionContext:
    item = Item(
        id=new_id(),
        tenant_id=tenant.id,
        source="manual",
        source_ref=str(new_id()),
        raw={},
        content={"title": "Hello"},
    )
    session.add(item)
    await session.flush()
    return ActionContext(session=session, tenant_id=tenant.id, item_id=item.id, option_id="A")


async def _rows(session: AsyncSession) -> list[ActionLog]:
    return list((await session.execute(select(ActionLog))).scalars())


async def test_same_params_twice_one_row_same_result(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    ctx = await _ctx(db_session, tenant)
    first = await run_action(ctx, "label", {"label": "urgent"})
    second = await run_action(ctx, "label", {"label": "urgent"})
    assert first.ok and second == first
    rows = await _rows(db_session)
    assert len(rows) == 1 and rows[0].status == "done" and rows[0].reversible


async def test_different_params_two_rows(db_session: AsyncSession, tenant: Tenant) -> None:
    ctx = await _ctx(db_session, tenant)
    await run_action(ctx, "label", {"label": "a"})
    await run_action(ctx, "label", {"label": "b"})
    assert len(await _rows(db_session)) == 2


async def test_extra_params_recorded_as_failed_and_repeat_is_stable(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    ctx = await _ctx(db_session, tenant)
    bad = await run_action(ctx, "archive", {"url": "https://x.test"})
    again = await run_action(ctx, "archive", {"url": "https://x.test"})
    assert not bad.ok and again == bad
    rows = await _rows(db_session)
    assert len(rows) == 1 and rows[0].status == "failed"


async def test_unknown_action(db_session: AsyncSession, tenant: Tenant) -> None:
    ctx = await _ctx(db_session, tenant)
    result = await run_action(ctx, "send_reply", {})
    assert not result.ok and result.error == "unknown_action"


async def test_remind_enqueues_job_and_reminder_due_emits_action_done(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    ctx = await _ctx(db_session, tenant)
    db_session.add(
        WebhookSubscription(
            id=new_id(),
            tenant_id=tenant.id,
            url="https://example.com/h",
            events=["action.done"],
            secret_enc="x",
            enabled=True,
        )
    )
    until = datetime.now(UTC) + timedelta(hours=2)
    result = await run_action(ctx, "remind", {"until": until.isoformat()})
    assert result.ok
    jobs = list(
        (await db_session.execute(select(Job).where(Job.kind == JobKind.ACTION.value))).scalars()
    )
    assert len(jobs) == 1 and jobs[0].payload["op"] == "reminder_due"
    await handle_action_job(db_session, jobs[0])
    hooks = list(
        (await db_session.execute(select(Job).where(Job.kind == JobKind.WEBHOOK.value))).scalars()
    )
    assert len(hooks) == 1
    assert hooks[0].payload["extra"] == {"action": "remind", "ok": True}


async def test_create_task_uses_item_title(db_session: AsyncSession, tenant: Tenant) -> None:
    ctx = await _ctx(db_session, tenant)
    result = await run_action(ctx, "create_task", {})
    assert result.ok and result.data["task"]["title"] == "Hello"
