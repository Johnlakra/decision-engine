"""A retried action never runs twice, including after a failure (FR-41)."""

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions import registry
from app.actions.registry import ActionContext, ActionDef, ActionResult, run_action
from app.core.ids import new_id
from app.models import ActionLog, Item, Tenant

pytestmark = pytest.mark.integration


class NoParams(BaseModel):
    pass


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    runs: list[int] = []

    async def flaky(ctx: ActionContext, params: NoParams) -> ActionResult:
        runs.append(1)
        raise RuntimeError("boom")

    async def fine(ctx: ActionContext, params: NoParams) -> ActionResult:
        runs.append(1)
        return ActionResult(True, {"n": len(runs)})

    monkeypatch.setitem(registry._ACTIONS, "t_flaky", ActionDef("t_flaky", flaky, False, NoParams))
    monkeypatch.setitem(registry._ACTIONS, "t_fine", ActionDef("t_fine", fine, False, NoParams))
    return runs


async def _ctx(session: AsyncSession, tenant: Tenant) -> ActionContext:
    item = Item(id=new_id(), tenant_id=tenant.id, source="m", source_ref=str(new_id()), raw={})
    session.add(item)
    await session.flush()
    return ActionContext(session=session, tenant_id=tenant.id, item_id=item.id)


async def test_raising_action_is_recorded_failed_and_not_rerun_on_retry(
    db_session: AsyncSession, tenant: Tenant, counted: list[int]
) -> None:
    ctx = await _ctx(db_session, tenant)

    first = await run_action(ctx, "t_flaky", {})
    retry = await run_action(ctx, "t_flaky", {})

    assert not first.ok and first.error == "RuntimeError"
    assert retry == first
    assert len(counted) == 1
    (row,) = (await db_session.scalars(select(ActionLog))).all()
    assert row.status == "failed"


async def test_success_retry_returns_stored_data_without_rerunning(
    db_session: AsyncSession, tenant: Tenant, counted: list[int]
) -> None:
    ctx = await _ctx(db_session, tenant)

    first = await run_action(ctx, "t_fine", {})
    for _ in range(3):
        assert await run_action(ctx, "t_fine", {}) == first

    assert counted == [1] and first.data == {"n": 1}


async def test_same_action_on_another_item_runs_again(
    db_session: AsyncSession, tenant: Tenant, counted: list[int]
) -> None:
    await run_action(await _ctx(db_session, tenant), "t_fine", {})
    await run_action(await _ctx(db_session, tenant), "t_fine", {})
    assert len(counted) == 2
