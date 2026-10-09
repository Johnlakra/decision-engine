"""SSRF guard bypass forms, and the guard re-checked at delivery time (NFR-05, FR-42)."""

import httpx
import pytest
import respx

from app.integrations.ssrf import UnsafeUrl, check_url
from app.integrations.webhooks_out import deliver_once
from tests.unit.integrations.test_envelope import (  # noqa: F401 - enc_key is an autouse fixture
    NOW,
    enc_key,
    make_pair,
)

BYPASS_URLS = [
    "https://localhost/hook",
    "https://127.1/hook",
    "https://2130706433/hook",  # decimal form of 127.0.0.1
    "https://0x7f.0.0.1/hook",
    "https://[::1]/hook",
    "https://[::ffff:169.254.169.254]/hook",
    "https://169.254.169.254/latest/meta-data",
    "https://user:pw@example.com/hook",
    "ftp://example.com/hook",
    "file:///etc/passwd",
    "https:///hook",
]


@pytest.mark.parametrize("url", BYPASS_URLS)
def test_bypass_forms_are_refused(url: str) -> None:
    with pytest.raises(UnsafeUrl):
        check_url(url, allow_private=False)


def test_dns_rebinding_to_private_address_is_refused() -> None:
    with pytest.raises(UnsafeUrl):
        check_url(
            "https://rebind.example.com/hook",
            allow_private=False,
            resolver=lambda host: ["93.184.216.34", "10.0.0.5"],
        )


@respx.mock
@pytest.mark.parametrize(
    "url", ["https://127.0.0.1/hook", "https://169.254.169.254/x", "https://[::1]/hook"]
)
async def test_delivery_refuses_a_stored_private_url_without_any_request(url: str) -> None:
    delivery, sub = make_pair()
    sub.url = url  # stored before the guard existed, or the DNS answer changed
    route = respx.post(url).mock(return_value=httpx.Response(200))

    outcome = await deliver_once(delivery, sub, now=NOW)

    assert not route.called and not respx.calls
    assert delivery.status == "pending" and delivery.attempts == 1
    assert outcome.retry_at is not None and not outcome.delivered
