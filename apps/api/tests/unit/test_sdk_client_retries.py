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
