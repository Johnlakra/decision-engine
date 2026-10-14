"""The radar bridge maps radar items onto the /v1/items contract (FR-96)."""

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from app.schemas.ingest import IngestItemIn

BRIDGE_PATH = Path(__file__).resolve().parents[5] / "examples" / "radar_bridge.py"


@pytest.fixture(scope="module")
def bridge() -> Iterator[ModuleType]:
    spec = importlib.util.spec_from_file_location("radar_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module


RADAR_ITEM = {
    "topic": "ai",
    "url": "https://example.com/launch",
    "title": "Model launch with free credits",
    "summary": "Credits for the first 1000 builders.",
    "source": "example.com",
    "score": 8,
    "category": "release",
    "action": "sign up",
    "urgency": "high",
    "why": "free credits",
    "personal": False,
    "fetched_at": "2026-10-06T08:00:00+00:00",
}


def test_mapped_body_validates_against_the_ingest_schema(bridge: ModuleType) -> None:
    body = bridge.map_radar_item(RADAR_ITEM)

    parsed = IngestItemIn.model_validate(body)

    assert parsed.source == "radar"
    assert parsed.source_ref == "https://example.com/launch"
    assert parsed.hints is not None and parsed.hints.niche == "news_radar"
    assert parsed.payload["score"] == 8  # radar score travels in the payload (FR-06)


def test_items_without_an_https_url_are_skipped(bridge: ModuleType) -> None:
    assert bridge.map_radar_item(dict(RADAR_ITEM, url="http://insecure.example")) is None
    assert bridge.map_radar_item(dict(RADAR_ITEM, url="")) is None


def test_overlong_urls_become_a_hashed_source_ref(bridge: ModuleType) -> None:
    long_url = "https://example.com/" + "a" * 400

    body = bridge.map_radar_item(dict(RADAR_ITEM, url=long_url))

    assert body is not None
    assert len(body["source_ref"]) == 64
    IngestItemIn.model_validate(body)


def test_post_sends_bearer_key_and_counts_failures(bridge: ModuleType) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = 201 if len(seen) == 1 else 422
        return httpx.Response(status, json={})

    bodies = bridge.map_all([RADAR_ITEM, dict(RADAR_ITEM, url="https://example.com/two")])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        accepted, failed = bridge.post_items(bodies, "https://de.example", "de_key", client)

    assert (accepted, failed) == (1, 1)
    assert seen[0].headers["Authorization"] == "Bearer de_key"
    assert str(seen[0].url) == "https://de.example/v1/items"
