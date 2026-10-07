"""HttpLayaClient against a respx-mocked Laya 0.3.27 wire format (FR-20, FR-22, NFR-03)."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.core.config import Settings
from app.triage.laya_client import HttpLayaClient
from tests.fakes.fake_laya import FakeLayaClient

BASE = "http://laya.test"
URL = f"{BASE}/v1/systemone/batch"
FIXTURES = Path(__file__).parent / "fixtures"
QUESTIONS: dict[str, Any] = {
    "needs_decision": {"type": "choice", "instructions": "x", "criteria": {"A": "yes", "B": "no"}}
}


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return data


def make(**kw: Any) -> HttpLayaClient:
    return HttpLayaClient(BASE, "secret-key", kw.pop("timeout_s", 2.0), **kw)


def echo(request: httpx.Request) -> httpx.Response:
    states = json.loads(request.content)["states"]
    results = [
        {
            "model": "laya-rl-agent",
            "usage": {},
            "answers": {
                "needs_decision": {
                    "type": "choice",
                    "choice": "A",
                    "confidence": 0.9,
                    "probabilities": {"A": 0.9, "B": 0.1},
                },
                "idx": {"type": "noul", "noul": int(s[1:]) / 100},
            },
            "routing": {"model": "english", "reason": "r"},
        }
        for s in states
    ]
    return httpx.Response(200, json={"results": results})


async def test_chunks_70_states_into_32_32_6_and_keeps_order() -> None:
    states = [f"s{i}" for i in range(70)]
    with respx.mock:
        route = respx.post(URL).mock(side_effect=echo)
        out = await make().batch(states, QUESTIONS)
    sizes = [len(json.loads(c.request.content)["states"]) for c in route.calls]
    assert sizes == [32, 32, 6]
    assert [round(r["answers"]["idx"]["noul"] * 100) for r in out if r] == list(range(70))


async def test_sends_bearer_header_and_no_model_by_default() -> None:
    with respx.mock:
        route = respx.post(URL).mock(side_effect=echo)
        await make().batch(["a"], QUESTIONS)
        sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer secret-key"
    assert "model" not in json.loads(sent.content)


async def test_model_override_is_forwarded() -> None:
    with respx.mock:
        route = respx.post(URL).mock(side_effect=echo)
        await make().batch(["a"], QUESTIONS, model="multilingual")
    assert json.loads(route.calls[0].request.content)["model"] == "multilingual"


async def test_timeout_gives_none_for_every_state() -> None:
    with respx.mock:
        respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
        out = await make().batch(["a", "b", "c"], QUESTIONS)
    assert out == [None, None, None]


async def test_one_bad_chunk_only_nones_that_chunk() -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom") if calls["n"] == 2 else echo(request)

    with respx.mock:
        respx.post(URL).mock(side_effect=flaky)
        out = await make(max_batch=2).batch([f"s{i}" for i in range(5)], QUESTIONS)
    assert [r is None for r in out] == [False, False, True, True, False]


async def test_503_retries_once_after_retry_after() -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = make(sleep=fake_sleep)
    with respx.mock:
        route = respx.post(URL).mock(
            side_effect=[
                httpx.Response(503, headers={"Retry-After": "1"}),
                httpx.Response(200, json={"results": [{"model": "m", "answers": {}}]}),
            ]
        )
        out = await client.batch(["a"], QUESTIONS)
    assert route.call_count == 2 and sleeps == [1.0]
    assert out[0] is not None


async def test_503_twice_gives_none() -> None:
    async def no_sleep(seconds: float) -> None:
        return None

    with respx.mock:
        route = respx.post(URL).mock(return_value=httpx.Response(503, headers={"Retry-After": "1"}))
        out = await make(sleep=no_sleep).batch(["a"], QUESTIONS)
    assert route.call_count == 2 and out == [None]


async def test_result_count_mismatch_and_garbage_give_none() -> None:
    with respx.mock:
        respx.post(URL).mock(return_value=httpx.Response(200, json={"results": []}))
        assert await make().batch(["a"], QUESTIONS) == [None]
        respx.post(URL).mock(return_value=httpx.Response(200, text="<html>"))
        assert await make().batch(["a"], QUESTIONS) == [None]


async def test_parses_choice_score_noul_from_full_payload() -> None:
    with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(200, json=fixture("batch_response_full.json"))
        )
        out = await make().batch(["a"], QUESTIONS)
    result = out[0]
    assert result is not None
    assert result["model"] == "english"
    assert result["laya_version"] is None or isinstance(result["laya_version"], str)
    assert isinstance(result["latency_ms"], int)
    nd = result["answers"]["needs_decision"]
    assert nd["choice"] == "A" and nd["probabilities"]["A"] == 0.91
    assert nd["confidence"] == 0.84 and nd["answer_confidence"] == 0.88
    urgency = result["answers"]["urgency"]
    assert urgency["level"] == 2 and urgency["score"] == 1.6
    keep = result["answers"]["keep"]
    assert keep["type"] == "noul" and keep["noul"] == 0.73 and keep["confidence"] == 0.73


async def test_parses_strict_payload_without_optional_fields() -> None:
    with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(200, json=fixture("batch_response_strict.json"))
        )
        result = (await make().batch(["a"], QUESTIONS))[0]
    assert result is not None
    assert result["model"] == "laya-rl-agent"
    assert result["answers"]["needs_decision"]["choice"] == "B"
    assert result["answers"]["needs_decision"]["answer_confidence"] == 0.6
    assert result["answers"]["keep"]["confidence"] == 0.8  # max(p, 1-p)


async def test_laya_version_read_from_header_when_present() -> None:
    with respx.mock:
        respx.post(URL).mock(
            return_value=httpx.Response(
                200,
                headers={"X-Laya-Version": "0.3.27"},
                json={"results": [{"model": "m", "answers": {}}]},
            )
        )
        result = (await make().batch(["a"], QUESTIONS))[0]
    assert result is not None and result["laya_version"] == "0.3.27"


async def test_empty_states_makes_no_call() -> None:
    with respx.mock:
        route = respx.post(URL).mock(side_effect=echo)
        assert await make().batch([], QUESTIONS) == []
    assert route.call_count == 0


async def test_health_ok_down_skipped() -> None:
    with respx.mock:
        respx.get(f"{BASE}/health").mock(
            return_value=httpx.Response(200, json=fixture("health.json"))
        )
        assert await make().health() == "ok"
        respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("no"))
        assert await make().health() == "down"
    assert await HttpLayaClient("", "k", 1.0).health() == "skipped"


def test_from_settings_none_when_url_empty() -> None:
    assert HttpLayaClient.from_settings(Settings(laya_url="")) is None  # type: ignore[call-arg]


def test_from_settings_builds_client() -> None:
    client = HttpLayaClient.from_settings(Settings(laya_url="http://x:8000/"))  # type: ignore[call-arg]
    assert client is not None and client.base_url == "http://x:8000"


async def test_fake_client_records_calls_and_is_confident() -> None:
    fake = FakeLayaClient()
    out = await fake.batch(["a", "b"], QUESTIONS)
    assert len(fake.calls) == 1 and out[0] is not None
    assert out[0]["answers"]["needs_decision"]["choice"] == "A"
    assert await FakeLayaClient(fail=True).batch(["a"], QUESTIONS) == [None]


@pytest.mark.parametrize("url", ["", "   "])
def test_blank_url_is_none(url: str) -> None:
    assert HttpLayaClient.from_settings(Settings(laya_url=url)) is None  # type: ignore[call-arg]
