"""Fakes for graph node unit tests: in-memory store, niche registry and gateway."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from app.graph import store
from app.graph.nodes import decide as decide_mod
from app.niches.registry import NicheRegistry, get_registry
from tests.fakes.fake_llm import FakeLLM, fake_llm

__all__ = ["FakeLLM", "fake_llm"]

ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="session")
def registry() -> NicheRegistry:
    reg = NicheRegistry(ROOT / "niches", ROOT / "schemas")
    reg.reload()
    return reg


class FakeStore:
    def __init__(self, view: store.ItemView) -> None:
        self.view = view
        self.entities: dict[str, Any] | None = None
        self.decision: dict[str, Any] | None = None
        self.route: tuple[str, bool] | None = None

    async def load_item_view(self, item_id: str) -> store.ItemView:
        return self.view

    async def apply_route(self, item_id: str, *, niche: str, informational: bool) -> None:
        self.route = (niche, informational)

    async def save_entities(self, item_id: str, entities: dict[str, Any]) -> None:
        self.entities = entities

    async def save_decision(self, item_id: str, decision: dict[str, Any]) -> None:
        self.decision = decision

    async def load_corrections(
        self, tenant_id: str, niche: str, limit: int, *, sensitivity: str = "public"
    ) -> list[Any]:
        return []


def make_view(**kw: Any) -> store.ItemView:
    base: dict[str, Any] = {
        "id": "i1",
        "tenant_id": "t1",
        "status": "triaged",
        "source": "manual",
        "sensitivity": "public",
        "language": "en",
        "niche": None,
        "risk": "normal",
        "triage": None,
        "content": {"title": "Brief", "body": "We need a stack"},
    }
    return store.ItemView(**{**base, **kw})


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch, registry: NicheRegistry) -> Iterator[FakeStore]:
    fake = FakeStore(make_view())
    for name in (
        "load_item_view",
        "apply_route",
        "save_entities",
        "save_decision",
        "load_corrections",
    ):
        monkeypatch.setattr(store, name, getattr(fake, name))
    import app.niches.registry as reg_mod

    monkeypatch.setattr(reg_mod, "_registry", registry)
    monkeypatch.setattr(decide_mod, "registered_actions", lambda: None)
    assert get_registry() is registry
    yield fake
