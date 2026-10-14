"""Notifier pass against Postgres: one ping per urgent item, quiet hours, retries (FR-43)."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.notify import run_notifications
from app.core.config import get_settings
from app.core.ids import new_id
from app.models import Item, Tenant
from app.models.enums import ItemStatus

pytestmark = pytest.mark.integration

OWNER_CHAT = "111"
# 04:30 UTC is 10:00 in Asia/Kolkata (daytime, digest due); 17:30 UTC is 23:00 (quiet hours).
DAYTIME = datetime(2026, 10, 14, 4, 30, tzinfo=UTC)
QUIET = datetime(2026, 10, 14, 17, 30, tzinfo=UTC)


@pytest_asyncio.fixture
async def bot(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", OWNER_CHAT)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def ok_transport(sent: list[dict[str, object]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(handler)


def failing_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(500))


def waiting_item(tenant: Tenant, ref: str, title: str, urgency: int) -> Item:
    return Item(
        id=new_id(),
        tenant_id=tenant.id,
        source="telegram",
        source_ref=ref,
        raw={"text": title},
        status=ItemStatus.AWAITING_APPROVAL.value,
        urgency=urgency,
        content={"title": title},
        decision={"rationale": "Free credits"},
        hints={"url": "https://example.com/offer"},
    )


async def test_urgent_item_is_pinged_once_and_the_digest_goes_once_a_day(
    db_session: AsyncSession, tenant: Tenant, bot: None
) -> None:
    db_session.add_all(
        [waiting_item(tenant, "a:1", "Urgent offer", 2), waiting_item(tenant, "a:2", "Later", 1)]
    )
    await db_session.flush()
    sent: list[dict[str, object]] = []

    first = await run_notifications(
        db_session, tenant.id, tenant.timezone, DAYTIME, transport=ok_transport(sent)
    )
    second = await run_notifications(
        db_session, tenant.id, tenant.timezone, DAYTIME, transport=ok_transport(sent)
    )

    assert (first.pings_sent, first.digest_sent) == (1, True)
    assert (second.pings_sent, second.digest_sent) == (0, False)
    pings = [message for message in sent if "reply_markup" in message]
    assert len(pings) == 1 and pings[0]["chat_id"] == OWNER_CHAT
    assert "Urgent offer" in str(pings[0]["text"])
    digests = [message for message in sent if "reply_markup" not in message]
    assert len(digests) == 1 and "Later" in str(digests[0]["text"])


async def test_quiet_hours_suppress_pings_but_items_stay_pending(
    db_session: AsyncSession, tenant: Tenant, bot: None
) -> None:
    db_session.add(waiting_item(tenant, "q:1", "Overnight", 2))
    await db_session.flush()
    sent: list[dict[str, object]] = []

    report = await run_notifications(
        db_session, tenant.id, tenant.timezone, QUIET, transport=ok_transport(sent)
    )

    assert report.pings_sent == 0
    assert all("reply_markup" not in message for message in sent)


async def test_a_failed_send_is_retried_on_the_next_run(
    db_session: AsyncSession, tenant: Tenant, bot: None
) -> None:
    item = waiting_item(tenant, "r:1", "Retry me", 2)
    db_session.add(item)
    await db_session.flush()

    failed = await run_notifications(
        db_session, tenant.id, tenant.timezone, DAYTIME, transport=failing_transport()
    )
    assert failed.pings_sent == 0 and failed.digest_sent is False
    assert item.notified_at is None

    sent: list[dict[str, object]] = []
    retried = await run_notifications(
        db_session, tenant.id, tenant.timezone, DAYTIME, transport=ok_transport(sent)
    )
    assert retried.pings_sent == 1
    assert item.notified_at is not None
