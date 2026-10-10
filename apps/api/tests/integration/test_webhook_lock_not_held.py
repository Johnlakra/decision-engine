"""The delivery row is not locked while the subscriber is being called (FR-42, NFR-05)."""

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.integrations.subscriptions import create_subscription
from app.integrations.webhooks_out import deliver
from app.models import Item, Job, Tenant, WebhookDelivery
from app.models.enums import JobKind

pytestmark = pytest.mark.integration
URL = "http://127.0.0.1:9/hook"


@pytest.fixture(autouse=True)
def webhook_env(settings_env: pytest.MonkeyPatch) -> None:
    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    settings_env.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())


@respx.mock
async def test_second_session_can_update_row_during_the_post(
    committed_db: async_sessionmaker[AsyncSession], tenant_committed: Tenant
) -> None:
    """FR-42: the FOR UPDATE lock is released before the HTTP call starts."""
    async with committed_db() as setup:
        item = Item(id=new_id(), tenant_id=tenant_committed.id, source="m", source_ref="l", raw={})
        setup.add(item)
        await setup.flush()
        sub = await create_subscription(
            setup,
            tenant_id=tenant_committed.id,
            url=URL,
            events=["decision.made"],
            secret="lock-test-secret-123",
        )
        delivery = WebhookDelivery(
            id=new_id(),
            tenant_id=tenant_committed.id,
            subscription_id=sub.id,
            event="decision.made",
            payload={"event": "decision.made", "id": "e1", "data": {}},
            status="pending",
            attempts=0,
        )
        job = Job(
            id=new_id(),
            tenant_id=tenant_committed.id,
            kind=JobKind.WEBHOOK.value,
            item_id=item.id,
            payload={"op": "deliver", "delivery_id": str(delivery.id)},
        )
        setup.add_all([delivery, job])
        await setup.commit()
    seen: dict[str, bool] = {}

    async def during_post(request: httpx.Request) -> httpx.Response:
        async with committed_db() as other:
            await other.execute(text("SET LOCAL lock_timeout = '1s'"))
            await other.execute(
                update(WebhookDelivery)
                .where(WebhookDelivery.id == delivery.id)
                .values(last_status_code=0)
            )
            await other.commit()
        seen["updated"] = True
        return httpx.Response(204)

    respx.post(URL).mock(side_effect=during_post)

    async with committed_db() as session:
        await deliver(session, job)
        await session.commit()

    assert seen == {"updated": True}
    async with committed_db() as check:
        row = (await check.scalars(select(WebhookDelivery))).one()
        assert (row.status, row.attempts, row.last_status_code) == ("delivered", 1, 204)
