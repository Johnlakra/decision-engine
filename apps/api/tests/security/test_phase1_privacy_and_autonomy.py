"""Phase 1 audit: private routing in /v1/decide and autonomy escalation (NFR-05, FR-34)."""

from typing import Any

import pytest

import app.niches.registry as reg_mod
from app.graph import oneshot, store
from app.graph.nodes.decide import filter_actions
from app.graph.nodes.policy import choose_autonomy
from app.niches.registry import NicheRegistry
from app.schemas.decision import ActionSpec, DecisionOut, Option
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import FakeLLM
from tests.unit.graph.conftest import ROOT
from tests.unit.graph.world import DECISION_OUT

QUESTIONS: dict[str, Any] = {
    "sell": {
        "type": "choice",
        "instructions": "Sell now or hold?",
        "criteria": {"A": "sell now", "B": "hold"},
    }
}


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> NicheRegistry:
    reg = NicheRegistry(ROOT / "niches", ROOT / "schemas")
    reg.reload()
    monkeypatch.setattr(reg_mod, "_registry", reg)

    async def corrections(
        tenant_id: str, niche: str, limit: int, *, sensitivity: str = "public"
    ) -> list[Any]:
        return []

    monkeypatch.setattr(store, "load_corrections", corrections)
    return reg


async def test_private_niche_with_public_body_never_reaches_public_provider(
    registry: NicheRegistry, fake_llm: FakeLLM
) -> None:
    inbox = registry.get("inbox")
    assert inbox is not None and inbox.sensitivity == "private"
    registry._niches["inbox"] = inbox.model_copy(update={"enabled": True})  # noqa: SLF001
    fake_llm.script("classify", {"sell": {"choice": "B", "confidence": 0.6}})
    fake_llm.script("normalise", {"entities": {}}, repeat=True).script("decide", DECISION_OUT)

    await oneshot.decide_oneshot(
        laya=FakeLayaClient(fail=True),
        tenant_id="t1",
        state="private mail body",
        questions=QUESTIONS,
        niche="inbox",
        explain=False,
        language="en",
        sensitivity="public",
    )

    assert {c.sensitivity for c in fake_llm.calls} == {"private"}


def _decision(*actions: str) -> DecisionOut:
    specs = [ActionSpec(type=a, params={"to": "attacker@evil.example"}) for a in actions]
    return DecisionOut(
        options=[Option(id="A", label="a", actions=specs), Option(id="B", label="b")],
        recommended="A",
        rationale="r",
        confidence=0.9,
    )


def test_model_chosen_action_outside_niche_list_is_dropped(registry: NicheRegistry) -> None:
    niche = registry.get("news_radar")
    assert niche is not None
    out = filter_actions(_decision("send_email", "archive"), frozenset(niche.actions), "i1")
    assert [a.type for a in out.options[0].actions] == ["archive"]


def test_auto_niche_cannot_be_escalated_by_non_auto_action(registry: NicheRegistry) -> None:
    niche = registry.get("news_radar")
    assert niche is not None and niche.autonomy == "auto"
    for actions in (("create_task",), ("archive", "webhook"), ()):
        got = choose_autonomy(niche, _decision(*actions), scam=False, expert=False)
        assert got == "ask", actions


def test_scam_and_expert_always_demote_auto(registry: NicheRegistry) -> None:
    niche = registry.get("news_radar")
    assert niche is not None
    assert choose_autonomy(niche, _decision("archive"), scam=True, expert=False) == "suggest"
    assert choose_autonomy(niche, _decision("archive"), scam=False, expert=True) == "ask"
