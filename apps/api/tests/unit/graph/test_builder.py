"""The compiled graph end to end with fakes and an in-memory checkpointer (FR-30, FR-33, NFR-03)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

import app.niches.registry as reg_mod
from app.graph.builder import build_graph
from app.graph.errors import UnsupportedSteps
from app.llm.errors import LLMUnavailable
from app.niches.registry import NicheRegistry
from tests.fakes.fake_llm import FakeLLM
from tests.unit.graph.conftest import ROOT
from tests.unit.graph.world import DECISION_OUT, FUTURE, World, install_world

CONFIG = {"configurable": {"thread_id": "i1"}}
START_STATE = {"item_id": "i1"}


class Crash(BaseException):  # noqa: N818 - BaseException so nothing in the graph can swallow it
    pass


def fresh_registry() -> NicheRegistry:
    registry = NicheRegistry(ROOT / "niches", ROOT / "schemas")
    registry.reload()
    return registry


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    monkeypatch.setattr(reg_mod, "_registry", fresh_registry())
    yield install_world(monkeypatch, World())


def graph() -> Any:
    return build_graph(InMemorySaver())


async def run(g: Any, payload: Any = START_STATE) -> dict[str, Any]:
    return await g.ainvoke(payload, CONFIG, durability="sync")  # type: ignore[no-any-return]


async def test_generic_item_waits_then_approve_runs_actions(
    world: World, fake_llm: FakeLLM
) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()

    first = await run(g)

    assert "__interrupt__" in first
    assert world.item.status == "awaiting_approval"
    assert world.events == ["decision.ready"]
    assert world.decision is not None and world.decision["autonomy"] == "ask"

    await run(g, Command(resume={"verdict": "approve"}))

    assert world.item.status == "done"
    assert [a["type"] for a in world.executed] == ["archive"]
    assert world.events == ["decision.ready", "decision.made", "action.done"]
    assert len(fake_llm.calls_for("decide")) == 1  # resume did not re-run decide
    assert not (await g.aget_state(CONFIG)).next


async def test_suggest_autonomy_approve_runs_no_actions(world: World, fake_llm: FakeLLM) -> None:
    world.view_fields["triage"] = {
        **world.view_fields["triage"],
        "answers": {
            **world.view_fields["triage"]["answers"],
            "niche": {
                "type": "choice",
                "choice": "tech_stack",
                "confidence": 0.9,
                "source": "hint",
            },
        },
    }
    fake_llm.script("normalise", {"entities": {}}, repeat=True)
    fake_llm.script(
        "decide",
        {
            **DECISION_OUT,
            "options": [
                {
                    "id": "A",
                    "label": "x",
                    "actions": [{"type": "create_task", "params": {"title": "t"}}],
                },
                {"id": "B", "label": "y", "actions": []},
            ],
        },
    )
    g = graph()
    await run(g)
    assert world.decision is not None and world.decision["autonomy"] == "suggest"

    await run(g, Command(resume={"verdict": "approve", "option": "A"}))

    assert world.item.status == "done"
    assert world.executed == []


async def test_reject_finishes_without_actions(world: World, fake_llm: FakeLLM) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()
    await run(g)

    await run(g, Command(resume={"verdict": "reject", "note": "no"}))

    assert world.item.status == "done"
    assert world.executed == []
    assert [d["verdict"] for d in world.decisions] == ["reject"]


async def test_informational_item_goes_to_done_without_llm(world: World, fake_llm: FakeLLM) -> None:
    world.view_fields["triage"] = {
        **world.view_fields["triage"],
        "answers": {
            **world.view_fields["triage"]["answers"],
            "needs_decision": {
                "type": "choice",
                "choice": "B",
                "confidence": 0.99,
                "source": "llm_fallback",
            },
        },
    }
    g = graph()

    result = await run(g)

    assert "__interrupt__" not in result
    assert world.item.status == "done"
    assert fake_llm.calls == []


async def test_snooze_loops_back_to_approval_until_unsnoozed(
    world: World, fake_llm: FakeLLM
) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()
    await run(g)

    snoozed = await run(
        g, Command(resume={"verdict": "snooze", "snooze_until": FUTURE().isoformat()})
    )

    assert "__interrupt__" in snoozed
    assert world.item.status == "snoozed"
    assert world.jobs[0]["op"] == "unsnooze"
    assert (await g.aget_state(CONFIG)).next == ("approval",)

    world.unsnooze()
    await run(g, Command(resume={"verdict": "approve", "option": "B"}))

    assert world.item.status == "done"
    assert [d["verdict"] for d in world.decisions] == ["snooze", "approve"]
    assert [a["type"] for a in world.executed] == ["remind"]
    assert len(fake_llm.calls_for("decide")) == 1


async def test_resume_replay_after_snooze_time_passed_still_completes(
    world: World, fake_llm: FakeLLM
) -> None:
    """M9: the graph must not re-apply the API's future-time check on resume."""
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()
    await run(g)
    past = datetime.now(UTC) - timedelta(hours=1)

    replayed = await run(g, Command(resume={"verdict": "snooze", "snooze_until": past.isoformat()}))

    assert "__interrupt__" in replayed
    assert world.item.status == "snoozed"
    assert [d["verdict"] for d in world.decisions] == ["snooze"]


async def test_auto_autonomy_approves_only_allow_listed_actions(
    world: World, fake_llm: FakeLLM
) -> None:
    registry = reg_mod._registry
    assert registry is not None
    generic = registry.get("generic")
    assert generic is not None
    registry._niches["generic"] = generic.model_copy(
        update={"autonomy": "auto", "auto_actions": ["archive"]}
    )
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()

    result = await run(g)

    assert "__interrupt__" not in result
    assert world.item.status == "done"
    assert [d["decided_by"] for d in world.decisions] == ["auto"]
    assert [a["type"] for a in world.executed] == ["archive"]
    assert "decision.ready" not in world.events


async def test_auto_autonomy_with_action_outside_auto_actions_asks(
    world: World, fake_llm: FakeLLM
) -> None:
    registry = reg_mod._registry
    assert registry is not None
    generic = registry.get("generic")
    assert generic is not None
    registry._niches["generic"] = generic.model_copy(
        update={"autonomy": "auto", "auto_actions": ["label"]}
    )
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)

    result = await run(graph())

    assert "__interrupt__" in result
    assert world.item.status == "awaiting_approval"
    assert world.executed == []


async def test_crash_in_decide_resumes_from_checkpoint_without_rerunning_extract(
    world: World, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.llm import gateway

    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    scripted = gateway.complete_json
    crashed: list[bool] = []

    async def crash_once(purpose: str, *args: Any, **kwargs: Any) -> Any:
        if purpose == "decide" and not crashed:
            crashed.append(True)
            raise Crash
        return await scripted(purpose, *args, **kwargs)

    monkeypatch.setattr(gateway, "complete_json", crash_once)
    g = graph()
    with pytest.raises(Crash):
        await run(g)
    assert world.item.status == "deciding"

    resumed = await run(g, None)

    assert "__interrupt__" in resumed
    assert world.item.status == "awaiting_approval"
    assert len(fake_llm.calls_for("normalise")) <= 1
    assert world.events == ["decision.ready"]


async def test_llm_unavailable_leaves_item_deciding_then_retry_succeeds(
    world: World, fake_llm: FakeLLM
) -> None:
    fake_llm.script("normalise", {"entities": {}}, repeat=True)
    fake_llm.script("decide", LLMUnavailable("down"), DECISION_OUT)
    g = graph()

    with pytest.raises(LLMUnavailable):
        await run(g)
    assert world.item.status == "deciding"

    result = await run(g, None)
    assert "__interrupt__" in result
    assert world.item.status == "awaiting_approval"


async def test_invalid_option_on_resume_raises_and_writes_nothing(
    world: World, fake_llm: FakeLLM
) -> None:
    """The runner validates first (a failed resume value is replayed by LangGraph on retry)."""
    from app.graph.errors import InvalidDecision

    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)
    g = graph()
    await run(g)

    with pytest.raises(InvalidDecision):
        await run(g, Command(resume={"verdict": "approve", "option": "E"}))

    assert world.item.status == "awaiting_approval"
    assert world.decisions == [] and world.events == ["decision.ready"]


def test_niche_with_custom_steps_is_rejected() -> None:
    registry = fresh_registry()
    generic = registry.get("generic")
    assert generic is not None
    registry._niches["generic"] = generic.model_copy(update={"steps": ["my_step"]})

    with pytest.raises(UnsupportedSteps, match="generic"):
        build_graph(InMemorySaver(), registry)
