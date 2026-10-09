"""Full retry ladder through the job queue, then dead-letter (FR-42, NFR-03)."""

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.time import utcnow
from app.integrations.events import emit
from app.integrations.subscriptions import create_subscription
from app.integrations.webhooks_out import RETRY_SCHEDULE_S, handle_webhook_job
from app.models import Item, Job, Tenant, WebhookDelivery
from app.models.enums import JobKind
from app.workers import queue
from tests.integration.acceptance._receiver import WebhookReceiver

pytestmark = pytest.mark.integration
SLACK = timedelta(seconds=5)


@pytest.fixture(autouse=True)
def webhook_env(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    settings_env.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())


async def _claim_one(session: AsyncSession) -> Job:
    jobs = await queue.claim(session, worker_id="t", limit=5, kinds=[JobKind.WEBHOOK])
    assert len(jobs) == 1
    return jobs[0]


async def _make_due(session: AsyncSession) -> None:
    await session.execute(
        update(Job).where(Job.status == "queued").values(run_at=utcnow() - timedelta(seconds=1))
    )


async def test_five_failures_follow_the_ladder_then_dead_letter(
    db_session: AsyncSession, tenant: Tenant
) -> None:
    item = Item(id=new_id(), tenant_id=tenant.id, source="manual", source_ref="dl", raw={"a": 1})
    db_session.add(item)
    await db_session.flush()
    with WebhookReceiver(default_status=500) as receiver:
        await create_subscription(
            db_session,
            tenant_id=tenant.id,
            url=receiver.url,
            events=["item.triaged"],
            secret="dead-letter-secret",
        )
        await emit(db_session, tenant_id=tenant.id, event="item.triaged", item_id=item.id)
        await handle_webhook_job(db_session, await _claim_one(db_session))  # fanout

        for attempt, delay in enumerate(RETRY_SCHEDULE_S, start=1):
            await handle_webhook_job(db_session, await _claim_one(db_session))
            delivery = (await db_session.scalars(select(WebhookDelivery))).one()
            assert (delivery.status, delivery.attempts) == ("pending", attempt)
            retry = (await db_session.scalars(select(Job).where(Job.status == "queued"))).one()
            expected = utcnow() + timedelta(seconds=delay)
            assert abs(retry.run_at - expected) < SLACK, f"attempt {attempt}"
            await _make_due(db_session)

        await handle_webhook_job(db_session, await _claim_one(db_session))  # 5th and last
        delivery = (await db_session.scalars(select(WebhookDelivery))).one()
        assert (delivery.status, delivery.attempts) == ("failed", len(RETRY_SCHEDULE_S) + 1)
        assert (await db_session.scalars(select(Job).where(Job.status == "queued"))).all() == []
        assert len(receiver.requests) == len(RETRY_SCHEDULE_S) + 1
