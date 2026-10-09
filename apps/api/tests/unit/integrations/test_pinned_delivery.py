"""Delivery connects to the vetted IP only, and ignores proxy env (NFR-05, FR-42)."""

import httpcore
import httpx
import pytest
import respx

from app.integrations import webhooks_out as wo
from app.integrations.pinned import PinnedBackend
from app.integrations.webhooks_out import deliver_once
from tests.unit.integrations.test_envelope import (  # noqa: F401 - enc_key is autouse
    NOW,
    enc_key,
    make_pair,
)

PUBLIC_IP = "93.184.216.34"


class RecordingBackend(httpcore.AsyncNetworkBackend):
    """Records every TCP connect and refuses it, so nothing leaves the test."""

    def __init__(self, fail_hosts: tuple[str, ...] = ()) -> None:
        self.connects: list[tuple[str, int]] = []
        self._fail_hosts = fail_hosts

    async def connect_tcp(  # type: ignore[no-untyped-def]
        self,
        host,
        port,
        timeout=None,  # noqa: ASYNC109
        local_address=None,
        socket_options=None,  # noqa: ASYNC109
    ):
        self.connects.append((host, port))
        raise httpcore.ConnectError(f"refused {host}")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):  # type: ignore[no-untyped-def]  # noqa: ASYNC109
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:
        return None


class FlipResolver:
    """Public at check time, loopback on every later lookup (DNS rebinding)."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, host: str) -> list[str]:
        self.calls += 1
        return [PUBLIC_IP] if self.calls == 1 else ["127.0.0.1"]


async def test_rebinding_resolver_never_connects_to_loopback() -> None:
    delivery, sub = make_pair()
    backend = RecordingBackend()
    resolver = FlipResolver()

    outcome = await deliver_once(delivery, sub, now=NOW, resolver=resolver, network_backend=backend)

    assert backend.connects == [(PUBLIC_IP, 443)]
    assert resolver.calls == 1  # connect never resolves again
    assert not outcome.delivered and outcome.retry_at is not None


async def test_pinned_backend_connects_only_to_vetted_addresses_in_order() -> None:
    inner = RecordingBackend()
    pinned = PinnedBackend("hook.example.com", ["1.1.1.1", "8.8.8.8"], inner=inner)

    with pytest.raises(httpcore.ConnectError):
        await pinned.connect_tcp("hook.example.com", 443)

    assert inner.connects == [("1.1.1.1", 443), ("8.8.8.8", 443)]


async def test_pinned_backend_refuses_other_hostnames() -> None:
    inner = RecordingBackend()
    pinned = PinnedBackend("hook.example.com", [PUBLIC_IP], inner=inner)

    with pytest.raises(httpcore.ConnectError):
        await pinned.connect_tcp("evil.example.net", 443)

    assert inner.connects == []


@respx.mock
async def test_request_keeps_original_hostname_in_url_and_host_header() -> None:
    delivery, sub = make_pair()
    route = respx.post(sub.url).mock(return_value=httpx.Response(204))

    outcome = await deliver_once(delivery, sub, now=NOW, resolver=lambda host: [PUBLIC_IP])

    request = route.calls.last.request
    assert request.url.host == "hook.example.com"
    assert request.headers["host"] == "hook.example.com"
    assert outcome.delivered


async def test_client_ignores_proxy_env_and_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    seen: dict[str, object] = {}
    real_client = httpx.AsyncClient

    def spy(*args: object, **kwargs: object) -> httpx.AsyncClient:
        seen.update(kwargs)
        return real_client(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(wo.httpx, "AsyncClient", spy)
    delivery, sub = make_pair()
    backend = RecordingBackend()

    await deliver_once(
        delivery, sub, now=NOW, resolver=lambda host: [PUBLIC_IP], network_backend=backend
    )

    assert seen["trust_env"] is False
    assert seen["follow_redirects"] is False
    assert backend.connects == [(PUBLIC_IP, 443)]  # not the proxy at 127.0.0.1
