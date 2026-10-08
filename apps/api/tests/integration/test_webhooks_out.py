"""Fan-out and delivery against Postgres with a real local receiver (FR-42, NFR-05)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.integrations.events import emit
from app.integrations.subscriptions import (
    InvalidSubscription,
    create_subscription,
    delete_subscription,
    list_deliveries,
)
from app.integrations.webhooks_out import handle_webhook_job
from app.models import Item, Job, Tenant, WebhookDelivery
from app.models.enums import JobKind
from app.security.hmac import verify
from app.workers import queue
from tests.integration.acceptance._receiver import WebhookReceiver

pytestmark = pytest.mark.integration
SECRET = "integration-secret-1234"


@pytest.fixture(autouse=True)
def allow_private(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    settings_env.setenv("TOKEN_ENC_KEY", _fernet_key())


def _fernet_key() -> str:
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


async def _jobs(session: AsyncSession) -> list[Job]:
    claimed = await queue.claim(session, worker_id="t", limit=10, kinds=[JobKind.WEBHOOK])
    return claimed


async def _item(session: AsyncSession, tenant: Tenant) -> Item:
    item = Item(
        id=new_id(), tenant_id=tenant.id, source="manual", source_ref=str(new_id()), raw={"a": 1}
    )
    session.add(item)
    await session.flush()
    return item


async def test_fanout_one_delivery_per_subscription_and_deliver(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    item = await _item(db_session, tenant)
    with WebhookReceiver() as receiver:
        for _ in range(2):
            await create_subscription(
                db_session,
                tenant_id=tenant.id,
                url=receiver.url,
                events=["decision.made"],
                secret=SECRET,
            )
        await emit(db_session, tenant_id=tenant.id, event="decision.made", item_id=item.id)
        (fanout_job,) = await _jobs(db_session)
        await handle_webhook_job(db_session, fanout_job)
        rows = (await db_session.scalars(select(WebhookDelivery))).all()
        assert len(rows) == 2
        for deliver_job in await _jobs(db_session):
            await handle_webhook_job(db_session, deliver_job)
        assert len(receiver.requests) == 2
        for request in receiver.requests:
            verify(SECRET.encode(), request.body, request.headers["X-DE-Signature"])
            assert "raw" not in request.json["data"]
    assert {d.status for d in await list_deliveries(db_session, tenant_id=tenant.id)} == {
        "delivered"
    }


async def test_failure_enqueues_retry_and_dead_letters(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    item = await _item(db_session, tenant)
    with WebhookReceiver(default_status=500) as receiver:
        await create_subscription(
            db_session,
            tenant_id=tenant.id,
            url=receiver.url,
            events=["item.triaged"],
            secret=SECRET,
        )
        await emit(db_session, tenant_id=tenant.id, event="item.triaged", item_id=item.id)
        (fanout_job,) = await _jobs(db_session)
        await handle_webhook_job(db_session, fanout_job)
        (deliver_job,) = await _jobs(db_session)
        await handle_webhook_job(db_session, deliver_job)
    delivery = (await db_session.scalars(select(WebhookDelivery))).one()
    assert delivery.attempts == 1 and delivery.status == "pending"
    retry = (
        await db_session.scalars(select(Job).where(Job.status == "queued", Job.kind == "webhook"))
    ).one()
    assert retry.payload["delivery_id"] == str(delivery.id)
    assert retry.run_at > delivery.updated_at


async def test_private_url_rejected_when_not_allowed(
    db_session: AsyncSession, tenant: Tenant, settings_env: pytest.MonkeyPatch
) -> None:
    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "false")
    with pytest.raises(InvalidSubscription):
        await create_subscription(
            db_session,
            tenant_id=tenant.id,
            url="https://127.0.0.1/hook",
            events=["decision.made"],
            secret=SECRET,
        )


async def test_delete_is_tenant_scoped(db_session: AsyncSession, tenant: Tenant) -> None:
    sub = await create_subscription(
        db_session,
        tenant_id=tenant.id,
        url="http://127.0.0.1:1/x",
        events=["decision.made"],
        secret=SECRET,
    )
    assert not await delete_subscription(db_session, tenant_id=new_id(), subscription_id=sub.id)
    assert await delete_subscription(db_session, tenant_id=tenant.id, subscription_id=sub.id)
