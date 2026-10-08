"""P3: a crash mid-graph resumes from the checkpoint, never restarts (NFR-03, FR-30)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

pytest.importorskip("app.graph.run")
pytest.importorskip("app.integrations.webhooks_out")
pytest.importorskip("app.tools.stack_catalog")

from app.llm import gateway  # noqa: E402
from app.models import WebhookDelivery  # noqa: E402
from app.workers import queue  # noqa: E402
from tests.fakes.fake_laya import FakeLayaClient  # noqa: E402

from ._pipeline import (  # noqa: E402
    SimulatedCrash,
    auth,
    load_item,
    post_item,
    run_worker_until_idle,
)
from ._receiver import WebhookReceiver  # noqa: E402
from ._scripts import SCHOOL_ERP_BRIEF, extract_calls  # noqa: E402

pytestmark = pytest.mark.integration


async def test_crash_in_decide_resumes_without_rerunning_extract(
    client, account, factory, llm, use_laya, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient())
    scripted = gateway.complete_json
    crashed: list[bool] = []

    async def crash_once_in_decide(purpose: str, *args: Any, **kwargs: Any) -> Any:
        if purpose == "decide" and not crashed:
            crashed.append(True)
            raise SimulatedCrash
        return await scripted(purpose, *args, **kwargs)

    monkeypatch.setattr(gateway, "complete_json", crash_once_in_decide)

    with WebhookReceiver() as receiver:
        subscribed = await client.post(
            "/v1/subscriptions",
            json={"url": receiver.url, "events": ["decision.ready"], "secret": "p3-secret"},
            headers=auth(account.key),
        )
        assert subscribed.status_code in (200, 201), subscribed.text
        item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p3-erp")

        # Act 1: the "process" dies while deciding; BaseException escapes Worker._process
        with pytest.raises(SimulatedCrash):
            await run_worker_until_idle(factory)
        assert (await load_item(factory, item_id)).status == "deciding"

        # Act 2: lease expires, job is reclaimed, a fresh worker run resumes
        async with factory() as session:
            assert await queue.reclaim_stale(session, lease=timedelta(0)) >= 1
            await session.commit()
        await run_worker_until_idle(factory)

    # Assert: finished, extract ran once in total (checkpoint resume), one decision.ready
    assert (await load_item(factory, item_id)).status == "awaiting_approval"
    assert len(extract_calls(llm)) == 1
    async with factory() as session:
        ready = await session.scalar(
            select(func.count())
            .select_from(WebhookDelivery)
            .where(WebhookDelivery.event == "decision.ready")
        )
    assert ready == 1
