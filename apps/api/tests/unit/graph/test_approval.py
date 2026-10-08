"""approval and act node behavior (FR-33, FR-34, FR-40, NFR-07)."""

from collections.abc import Iterator
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import app.niches.registry as reg_mod
from app.graph.builder import build_graph
from app.graph.nodes.act import act, chosen_actions
from app.tools.registry import registered as registered_tools
from tests.fakes.fake_llm import FakeLLM
from tests.unit.graph.test_builder import CONFIG, START_STATE, fresh_registry
from tests.unit.graph.world import DECISION_OUT, World, install_world


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.setattr(reg_mod, "_registry", fresh_registry())
    yield install_world(monkeypatch, World())


def test_stack_catalog_tools_register_on_package_import() -> None:
    assert {"stack_catalog.shortlist", "stack_catalog.free_tiers"} <= registered_tools()


async def test_interrupt_payload_carries_item_id_and_decision(
    world: World, fake_llm: FakeLLM
) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    graph = build_graph(InMemorySaver())

    result = await graph.ainvoke(START_STATE, CONFIG, durability="sync")

    payload = result["__interrupt__"][0].value
    assert payload["item_id"] == "i1"
    assert payload["decision"]["recommended"] == "A"
    assert payload["decision"]["ready_at"]


async def test_edit_verdict_runs_edited_actions_only_if_allowed(
    world: World, fake_llm: FakeLLM
) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    graph = build_graph(InMemorySaver())
    await graph.ainvoke(START_STATE, CONFIG, durability="sync")
    edits = {"actions": [{"type": "remind", "params": {}}, {"type": "wire_money"}]}

    await graph.ainvoke(
        Command(resume={"verdict": "edit", "option": "A", "edits": edits}),
        CONFIG,
        durability="sync",
    )

    assert [a["type"] for a in world.executed] == ["remind"]


def test_chosen_actions_falls_back_to_option_when_edits_invalid() -> None:
    state: Any = {
        "item_id": "i1",
        "decision": DECISION_OUT,
        "verdict": {"verdict": "edit", "option": "B", "edits": {"actions": [{"nope": 1}]}},
    }
    assert [a["type"] for a in chosen_actions(state)] == ["remind"]


async def test_act_does_nothing_for_reject(world: World) -> None:
    state: Any = {"item_id": "i1", "tenant_id": "t1", "verdict": {"verdict": "reject"}}
    assert await act(state) == {"actions_done": []}
    assert world.executed == []
