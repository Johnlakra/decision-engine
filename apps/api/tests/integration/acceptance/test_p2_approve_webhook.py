"""P2: approve resumes the graph and delivers a signed decision.made webhook (FR-33, FR-42)."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

pytest.importorskip("app.graph.run")
pytest.importorskip("app.integrations.webhooks_out")
pytest.importorskip("app.tools.stack_catalog")

from app.core.time import utcnow  # noqa: E402
from app.models import Decision, Feedback, Job, WebhookDelivery  # noqa: E402
from app.security.hmac import verify  # noqa: E402
from tests.fakes.fake_laya import FakeLayaClient  # noqa: E402

from ._pipeline import auth, load_item, post_item, run_worker_until_idle  # noqa: E402
from ._receiver import WebhookReceiver  # noqa: E402
from ._scripts import SCHOOL_ERP_BRIEF  # noqa: E402

pytestmark = pytest.mark.integration

SECRET = "s3cr3t-for-acceptance"
FIRST_RETRY_S = 60


async def test_approve_delivers_signed_webhook_with_retry_and_single_feedback(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient())
    with WebhookReceiver(statuses=[500, 200]) as receiver:
        # Arrange: subscribe, then bring an item to awaiting_approval
        created = await client.post(
            "/v1/subscriptions",
            json={"url": receiver.url, "events": ["decision.made"], "secret": SECRET},
            headers=auth(account.key),
        )
        assert created.status_code in (200, 201), created.text
        item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p2-erp")
        await run_worker_until_idle(factory)
        assert (await load_item(factory, item_id)).status == "awaiting_approval"

        # Act: approve
        response = await client.post(
            f"/v1/items/{item_id}/decision", json={"verdict": "approve"}, headers=auth(account.key)
        )

        # Assert: resume answered inline
        assert response.status_code == 200, response.text
        assert response.json() == {"status": "done"}

        # Act: first delivery attempt hits the 500
        await run_worker_until_idle(factory)

        # Assert: attempt recorded, retry due in about 60 s (FR-42)
        async with factory() as session:
            delivery = (await session.scalars(select(WebhookDelivery))).one()
        assert len(receiver.requests) == 1
        assert delivery.attempts == 1 and delivery.status == "pending"
        wait = (delivery.next_attempt_at - utcnow()).total_seconds()
        assert FIRST_RETRY_S - 20 <= wait <= FIRST_RETRY_S + 5

        # Act: force the retry due and run again
        async with factory() as session:
            past = utcnow() - timedelta(seconds=1)
            await session.execute(update(WebhookDelivery).values(next_attempt_at=past))
            await session.execute(update(Job).where(Job.kind == "webhook").values(run_at=past))
            await session.commit()
        await run_worker_until_idle(factory)

        # Assert: delivered, signed, addressed to this item
        assert len(receiver.requests) == 2
        for request in receiver.requests:
            verify(SECRET.encode(), request.body, request.headers["X-DE-Signature"])
            assert request.json["event"] == "decision.made"
            assert request.json["data"]["id"] == item_id
            assert "raw" not in request.json["data"] and "hints" not in request.json["data"]

    async with factory() as session:
        delivery = (await session.scalars(select(WebhookDelivery))).one()
        decisions = await session.scalar(select(func.count()).select_from(Decision))
        feedback = (await session.scalars(select(Feedback))).all()
    assert delivery.status == "delivered"
    assert decisions == 1
    assert [f.kind for f in feedback] == ["decision"]
