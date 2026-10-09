"""Envelope, retry schedule and delivery outcome (FR-42, NFR-05)."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.integrations import webhooks_out as wo
from app.integrations.webhooks_out import RETRY_SCHEDULE_S, build_envelope, deliver_once, serialize
from app.models import Item, WebhookDelivery, WebhookSubscription
from app.security.crypto import encrypt
from app.security.hmac import verify

_KEY = Fernet.generate_key().decode()
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
SECRET = "whsec-test"
URL = "https://hook.example.com/in"


def make_item() -> Item:
    return Item(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        source="webhook",
        source_ref="r1",
        raw={"secret": "RAW-SHOULD-NOT-LEAK"},
        hints={"niche": "HINT-SHOULD-NOT-LEAK"},
        callback_url="https://cb.example.com/CALLBACK",
        status="awaiting_approval",
        sensitivity="public",
        received_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def test_schedule_is_contract() -> None:
    assert RETRY_SCHEDULE_S == (60, 300, 1800, 7200)


def test_envelope_never_leaks_raw_hints_or_callback() -> None:
    envelope = build_envelope(
        event="decision.made",
        event_id="evt_1",
        created_at=NOW,
        item=make_item(),
        last_decision=None,
    )
    text = serialize(envelope).decode()
    for leak in ("RAW-SHOULD-NOT-LEAK", "HINT-SHOULD-NOT-LEAK", "CALLBACK", "callback_url"):
        assert leak not in text
    assert envelope["event"] == "decision.made" and envelope["id"] == "evt_1"
    assert envelope["created_at"] == "2026-10-08T12:00:00Z"


def test_action_done_carries_action_and_ok() -> None:
    envelope = build_envelope(
        event="action.done",
        event_id="evt_2",
        created_at=NOW,
        item=make_item(),
        last_decision=None,
        extra={"action": "set_reminder", "ok": True, "junk": 1},
    )
    assert envelope["data"]["action"] == "set_reminder"
    assert envelope["data"]["ok"] is True
    assert "junk" not in envelope["data"]


def test_serialize_is_stable() -> None:
    assert serialize({"b": 1, "a": 2}) == serialize({"a": 2, "b": 1})


def make_pair(attempts: int = 0) -> tuple[WebhookDelivery, WebhookSubscription]:
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        url=URL,
        events=["decision.made"],
        secret_enc=encrypt(SECRET, key=_KEY),
        enabled=True,
    )
    delivery = WebhookDelivery(
        id=uuid.uuid4(),
        tenant_id=sub.tenant_id,
        subscription_id=sub.id,
        event="decision.made",
        payload={"event": "decision.made", "id": "evt_9", "data": {"id": "x"}},
        status="pending",
        attempts=attempts,
    )
    return delivery, sub


@pytest.fixture(autouse=True)
def enc_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TOKEN_ENC_KEY", _KEY)
    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def public(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wo, "check_url", lambda url, *, allow_private, resolver=None: [])


@respx.mock
async def test_2xx_marks_delivered_and_signs(monkeypatch: pytest.MonkeyPatch) -> None:
    public(monkeypatch)
    delivery, sub = make_pair()
    route = respx.post(URL).mock(return_value=httpx.Response(204))
    outcome = await deliver_once(delivery, sub, now=NOW)
    request = route.calls.last.request
    verify(SECRET.encode(), request.content, request.headers["X-DE-Signature"])
    assert request.headers["X-DE-Event"] == "decision.made"
    assert request.headers["X-DE-Delivery"] == str(delivery.id)
    assert json.loads(request.content)["id"] == "evt_9"
    assert delivery.status == "delivered" and delivery.attempts == 1
    assert delivery.last_status_code == 204
    assert outcome.retry_at is None


@respx.mock
@pytest.mark.parametrize("attempts_before,delay", [(0, 60), (1, 300), (2, 1800), (3, 7200)])
async def test_failure_schedules_retry(
    monkeypatch: pytest.MonkeyPatch, attempts_before: int, delay: int
) -> None:
    public(monkeypatch)
    delivery, sub = make_pair(attempts_before)
    respx.post(URL).mock(return_value=httpx.Response(500))
    outcome = await deliver_once(delivery, sub, now=NOW)
    assert delivery.status == "pending" and delivery.attempts == attempts_before + 1
    assert delivery.last_status_code == 500
    assert delivery.next_attempt_at == NOW + timedelta(seconds=delay)
    assert outcome.retry_at == delivery.next_attempt_at


@respx.mock
async def test_fifth_failure_is_dead_letter(monkeypatch: pytest.MonkeyPatch) -> None:
    public(monkeypatch)
    delivery, sub = make_pair(4)
    respx.post(URL).mock(return_value=httpx.Response(503))
    outcome = await deliver_once(delivery, sub, now=NOW)
    assert delivery.status == "failed" and delivery.attempts == 5
    assert outcome.retry_at is None


@respx.mock
async def test_redirect_is_a_failure_and_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    public(monkeypatch)
    delivery, sub = make_pair()
    respx.post(URL).mock(
        return_value=httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
    )
    target = respx.post("http://169.254.169.254/").mock(return_value=httpx.Response(200))
    await deliver_once(delivery, sub, now=NOW)
    assert not target.called
    assert delivery.status == "pending" and delivery.last_status_code == 302


@respx.mock
async def test_network_error_is_a_failed_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    public(monkeypatch)
    delivery, sub = make_pair()
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    await deliver_once(delivery, sub, now=NOW)
    assert delivery.status == "pending" and delivery.attempts == 1
    assert delivery.last_status_code is None


@respx.mock
async def test_unsafe_url_is_refused_without_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.ssrf import UnsafeUrl

    def refuse(url: str, *, allow_private: bool, resolver: object = None) -> list[str]:
        raise UnsafeUrl("private")

    monkeypatch.setattr(wo, "check_url", refuse)
    delivery, sub = make_pair()
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    await deliver_once(delivery, sub, now=NOW)
    assert not route.called
    assert delivery.status == "pending" and delivery.attempts == 1


@respx.mock
async def test_secret_not_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    public(monkeypatch)
    caplog.set_level("DEBUG")
    delivery, sub = make_pair()
    respx.post(URL).mock(return_value=httpx.Response(500))
    await deliver_once(delivery, sub, now=NOW)
    assert SECRET not in caplog.text
