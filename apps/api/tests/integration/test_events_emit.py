"""emit() against real Postgres: same-transaction semantics (FR-42)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.integrations.events import emit
from app.models import Item, Job, Tenant, WebhookSubscription
from app.models.enums import JobKind

pytestmark = pytest.mark.integration


async def _item(session: AsyncSession, tenant: Tenant) -> Item:
    item = Item(id=new_id(), tenant_id=tenant.id, source="manual", source_ref=str(new_id()), raw={})
    session.add(item)
    await session.flush()
    return item


def _sub(tenant: Tenant, events: list[str], enabled: bool = True) -> WebhookSubscription:
    return WebhookSubscription(
        id=new_id(),
        tenant_id=tenant.id,
        url="https://example.com/hook",
        events=events,
        secret_enc="x",
        enabled=enabled,
    )


async def _webhook_jobs(session: AsyncSession) -> list[Job]:
    rows = await session.execute(select(Job).where(Job.kind == JobKind.WEBHOOK.value))
    return list(rows.scalars())


async def test_no_subscription_no_job(db_session: AsyncSession, tenant: Tenant) -> None:
    item = await _item(db_session, tenant)
    await emit(db_session, tenant_id=tenant.id, event="item.triaged", item_id=item.id)
    assert await _webhook_jobs(db_session) == []


async def test_matching_subscription_one_job(db_session: AsyncSession, tenant: Tenant) -> None:
    item = await _item(db_session, tenant)
    db_session.add(_sub(tenant, ["decision.made", "item.triaged"]))
    await db_session.flush()
    await emit(db_session, tenant_id=tenant.id, event="decision.made", item_id=item.id)
    jobs = await _webhook_jobs(db_session)
    assert len(jobs) == 1
    assert jobs[0].payload["op"] == "fanout"
    assert jobs[0].item_id == item.id


async def test_other_event_or_disabled_ignored(db_session: AsyncSession, tenant: Tenant) -> None:
    item = await _item(db_session, tenant)
    db_session.add(_sub(tenant, ["action.done"]))
    db_session.add(_sub(tenant, ["decision.made"], enabled=False))
    await db_session.flush()
    await emit(db_session, tenant_id=tenant.id, event="decision.made", item_id=item.id)
    assert await _webhook_jobs(db_session) == []


async def test_rollback_discards_job(db_session: AsyncSession, tenant: Tenant) -> None:
    item = await _item(db_session, tenant)
    db_session.add(_sub(tenant, ["decision.made"]))
    await db_session.flush()
    nested = await db_session.begin_nested()
    await emit(db_session, tenant_id=tenant.id, event="decision.made", item_id=item.id)
    await nested.rollback()
    assert await _webhook_jobs(db_session) == []
