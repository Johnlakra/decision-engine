"""A permanent crypto error dead-letters the delivery instead of raising (FR-42, NFR-07)."""

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.integrations.webhooks_out import deliver_once
from tests.unit.integrations.test_envelope import (  # noqa: F401 - enc_key is autouse
    NOW,
    URL,
    enc_key,
    make_pair,
    public,
)


@respx.mock
async def test_corrupt_secret_dead_letters_without_request(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """FR-42, NFR-07: DecryptError is a permanent failure, not an exception or a retry."""
    public(monkeypatch)
    caplog.set_level("DEBUG")
    route = respx.post(URL).mock(return_value=httpx.Response(200))
    delivery, sub = make_pair()
    sub.secret_enc = "not-a-fernet-token"

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert not route.called
    assert outcome.retry_at is None and not outcome.delivered
    assert delivery.status == "failed" and delivery.attempts == 1
    assert str(delivery.id) in caplog.text and "DecryptError" in caplog.text
    assert "not-a-fernet-token" not in caplog.text


@respx.mock
async def test_missing_encryption_key_dead_letters(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-42, NFR-07: CryptoNotConfigured is a permanent failure too."""
    public(monkeypatch)
    delivery, sub = make_pair()
    monkeypatch.setenv("TOKEN_ENC_KEY", "")
    get_settings.cache_clear()
    route = respx.post(URL).mock(return_value=httpx.Response(200))

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert not route.called and outcome.retry_at is None
    assert delivery.status == "failed" and delivery.attempts == 1
