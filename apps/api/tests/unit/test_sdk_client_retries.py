"""Python SDK wrapper retries 429/5xx and sends the bearer key (FR-96)."""

import sys
from pathlib import Path

import httpx
import pytest
import respx

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "packages/client-py/src"))

from decision_engine_client import DecisionEngine  # noqa: E402
from decision_engine_client._generated.models import (  # noqa: E402
    IngestItemIn,
    IngestItemInPayloadType0,
)

BASE = "http://engine.test"
OK = {"id": "0199c0de-0000-7000-8000-000000000001", "status": "queued", "duplicate": False}


def _body() -> IngestItemIn:
    return IngestItemIn(payload=IngestItemInPayloadType0(), source="radar", source_ref="r-1")


def _engine(sleeps: list[float], retries: int = 3) -> DecisionEngine:
    return DecisionEngine(BASE, "de_test_placeholder", retries=retries, sleep=sleeps.append)


@respx.mock
def test_retries_5xx_then_succeeds() -> None:
    route = respx.post(f"{BASE}/v1/items").mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(202, json=OK)]
    )
    sleeps: list[float] = []
    result = _engine(sleeps).create_item(_body())
    assert route.call_count == 3
    assert str(result.id) == OK["id"]
    assert len(sleeps) == 2


@respx.mock
def test_honours_retry_after_on_429() -> None:
    respx.post(f"{BASE}/v1/items").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(202, json=OK),
        ]
    )
    sleeps: list[float] = []
    _engine(sleeps).create_item(_body())
    assert sleeps == [7.0]


@respx.mock
def test_sends_bearer_key() -> None:
    route = respx.post(f"{BASE}/v1/items").mock(return_value=httpx.Response(202, json=OK))
    _engine([]).create_item(_body())
    assert route.calls.last.request.headers["authorization"] == "Bearer de_test_placeholder"


@respx.mock
def test_gives_up_after_configured_retries() -> None:
    route = respx.post(f"{BASE}/v1/items").mock(return_value=httpx.Response(500))
    with pytest.raises(Exception):  # noqa: B017 - generated UnexpectedStatus
        _engine([], retries=2).create_item(_body())
    assert route.call_count == 3


@respx.mock
def test_does_not_retry_client_errors() -> None:
    route = respx.post(f"{BASE}/v1/items").mock(return_value=httpx.Response(401))
    with pytest.raises(Exception):  # noqa: B017
        _engine([]).create_item(_body())
    assert route.call_count == 1


# --- retry policy: method + path allow-list (FR-111) ---

DECIDE_OK = {
    "needs_decision": False,
    "niche": "generic",
    "urgency": "low",
    "risk": "low",
    "confidence": 0.9,
    "summary": "",
    "options": [],
    "recommendation": None,
    "rationale": "",
    "latency_ms": 1,
}
ITEM_ID = "0199c0de-0000-7000-8000-000000000001"


def _decide_body() -> object:
    from decision_engine_client._generated.models import DecideIn

    return DecideIn(state="hello")


def _decision_body() -> object:
    from decision_engine_client._generated.models import DecisionIn

    return DecisionIn(verdict="approve")


def _transport(responses: list[object], sleeps: list[float], retries: int = 3):
    from decision_engine_client.client import RetryTransport

    calls: list[httpx.Request] = []

    class Inner(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            calls.append(request)
            item = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(item, Exception):
                raise item
            assert isinstance(item, httpx.Response)
            return item

    return RetryTransport(retries, inner=Inner(), sleep=sleeps.append), calls


def _send(transport, method: str, path: str) -> httpx.Response | Exception:
    try:
        return transport.handle_request(httpx.Request(method, f"{BASE}{path}"))
    except httpx.HTTPError as exc:
        return exc


def test_get_retries_5xx_and_read_timeout() -> None:
    transport, calls = _transport(
        [httpx.ReadTimeout("t"), httpx.Response(500), httpx.Response(200)], []
    )
    result = _send(transport, "GET", f"/v1/items/{ITEM_ID}")
    assert isinstance(result, httpx.Response) and result.status_code == 200
    assert len(calls) == 3


@pytest.mark.parametrize("path", ["/v1/items", "/v1/items/bulk"])
def test_ingest_posts_retry_5xx(path: str) -> None:
    transport, calls = _transport([httpx.Response(503), httpx.Response(202)], [])
    result = _send(transport, "POST", path)
    assert isinstance(result, httpx.Response) and result.status_code == 202
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [httpx.Response(500), httpx.Response(503), httpx.Response(429), httpx.ReadTimeout("t")],
)
def test_decide_never_retries_without_retry_after(response: object) -> None:
    transport, calls = _transport([response], [])
    _send(transport, "POST", "/v1/decide")
    assert len(calls) == 1


def test_decide_retries_429_with_retry_after() -> None:
    sleeps: list[float] = []
    transport, calls = _transport(
        [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200)], sleeps
    )
    result = _send(transport, "POST", "/v1/decide")
    assert isinstance(result, httpx.Response) and result.status_code == 200
    assert len(calls) == 2 and sleeps == [2.0]


@respx.mock
def test_decide_500_called_once_through_facade() -> None:
    route = respx.post(f"{BASE}/v1/decide").mock(return_value=httpx.Response(500))
    with pytest.raises(Exception):  # noqa: B017
        _engine([]).decide(_decide_body())
    assert route.call_count == 1


@respx.mock
def test_decide_read_timeout_called_once_through_facade() -> None:
    route = respx.post(f"{BASE}/v1/decide").mock(side_effect=httpx.ReadTimeout("t"))
    with pytest.raises(httpx.ReadTimeout):
        _engine([]).decide(_decide_body())
    assert route.call_count == 1


@respx.mock
def test_decision_500_called_once_through_facade() -> None:
    from uuid import UUID

    route = respx.post(f"{BASE}/v1/items/{ITEM_ID}/decision").mock(return_value=httpx.Response(500))
    with pytest.raises(Exception):  # noqa: B017
        _engine([]).decide_item(UUID(ITEM_ID), _decision_body())
    assert route.call_count == 1


def test_decision_retries_only_429_with_retry_after() -> None:
    path = f"/v1/items/{ITEM_ID}/decision"
    for response in (httpx.Response(500), httpx.ReadTimeout("t"), httpx.Response(429)):
        transport, calls = _transport([response], [])
        _send(transport, "POST", path)
        assert len(calls) == 1
    transport, calls = _transport(
        [httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200)], []
    )
    _send(transport, "POST", path)
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/v1/subscriptions"), ("DELETE", "/v1/subscriptions/abc"), ("PATCH", "/v1/items/x")],
)
def test_other_calls_retry_only_429_with_retry_after(method: str, path: str) -> None:
    for response in (httpx.Response(500), httpx.ReadTimeout("t"), httpx.Response(429)):
        transport, calls = _transport([response], [])
        _send(transport, method, path)
        assert len(calls) == 1
    transport, calls = _transport(
        [httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200)], []
    )
    _send(transport, method, path)
    assert len(calls) == 2


def test_decide_timeout_is_at_least_35_seconds() -> None:
    engine = DecisionEngine(BASE, "k", timeout=10)
    assert engine.decide_timeout >= 35
    assert DecisionEngine(BASE, "k", timeout=60).decide_timeout == 60
