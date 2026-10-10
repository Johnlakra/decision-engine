"""Delivery is bounded in time and bytes, and crypto errors dead-letter (FR-42, NFR-05)."""

import time
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.integrations import webhooks_out as wo
from app.integrations.webhooks_out import MAX_RESPONSE_BYTES, deliver_once
from tests.unit.integrations.test_envelope import (  # noqa: F401 - enc_key is autouse
    NOW,
    URL,
    enc_key,
    make_pair,
    public,
)

CHUNK = 16 * 1024


class EndlessBody(httpx.AsyncByteStream):
    """Streams chunks forever and records how many bytes the client pulled."""

    def __init__(self) -> None:
        self.sent = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        while True:
            self.sent += CHUNK
            yield b"x" * CHUNK


@respx.mock
async def test_slow_receiver_is_cut_off_by_total_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-42: httpx per-operation timeouts are not enough; the whole call is bounded."""
    import asyncio

    public(monkeypatch)
    monkeypatch.setenv("WEBHOOK_TIMEOUT_SECONDS", "0.2")
    get_settings.cache_clear()

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        return httpx.Response(200)

    respx.post(URL).mock(side_effect=slow)
    delivery, sub = make_pair()
    started = time.monotonic()

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert time.monotonic() - started < 5
    assert not outcome.delivered and outcome.retry_at is not None
    assert delivery.status == "pending" and delivery.attempts == 1
    assert delivery.last_status_code is None


@respx.mock
async def test_oversized_2xx_body_is_cut_off_and_still_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-42: a 2xx with a huge body counts as delivered; reading stops at the cap."""
    public(monkeypatch)
    body = EndlessBody()
    respx.post(URL).mock(return_value=httpx.Response(200, stream=body))
    delivery, sub = make_pair()

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert outcome.delivered and delivery.status == "delivered"
    assert delivery.last_status_code == 200
    assert MAX_RESPONSE_BYTES <= body.sent <= MAX_RESPONSE_BYTES + 2 * CHUNK


@respx.mock
async def test_oversized_error_body_is_cut_off_and_counted_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-42: a 500 with a huge body is a normal failed attempt with a bounded read."""
    public(monkeypatch)
    body = EndlessBody()
    respx.post(URL).mock(return_value=httpx.Response(500, stream=body))
    delivery, sub = make_pair()

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert not outcome.delivered and outcome.retry_at is not None
    assert delivery.last_status_code == 500 and delivery.attempts == 1
    assert body.sent <= MAX_RESPONSE_BYTES + 2 * CHUNK


@respx.mock
async def test_signature_bytes_identical_across_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-42: every retry sends exactly the same body."""
    public(monkeypatch)
    route = respx.post(URL).mock(return_value=httpx.Response(500))
    delivery, sub = make_pair()

    await deliver_once(delivery, sub, now=NOW)
    await deliver_once(delivery, sub, now=NOW)

    first, second = (call.request.content for call in route.calls)
    assert first == second


def test_wo_exposes_response_cap_constant() -> None:
    """NFR-05: the cap is a named constant of 64 KiB."""
    assert wo.MAX_RESPONSE_BYTES == 64 * 1024
