"""Policy (FR-25, FR-34)."""

from typing import Any

import pytest

from app.graph.nodes.policy import (
    SCAM_WARNING,
    choose_autonomy,
    is_scam,
    policy,
    scam_suspected,
)
from app.niches.registry import get_registry
from app.schemas.decision import DecisionOut
from tests.unit.graph.conftest import FakeStore, make_view

DECISION: dict[str, Any] = {
    "options": [
        {"id": "A", "label": "Archive", "actions": [{"type": "archive"}]},
        {"id": "B", "label": "Other", "actions": [{"type": "notify"}]},
    ],
    "recommended": "A",
    "rationale": "r",
    "evidence": [],
    "confidence": 0.8,
}


async def test_scam_forces_suggest_with_warning(fake_store: FakeStore) -> None:
    fake_store.view = make_view(
        risk="scam_or_phishing", triage={"answers": {"risk": {"confidence": 0.9}}}
    )
    out = await policy({"item_id": "i1", "niche": "generic", "decision": DECISION})
    assert out["decision"]["autonomy"] == "suggest"
    assert SCAM_WARNING in out["decision"]["warnings"]
    assert fake_store.decision == out["decision"]


async def test_low_confidence_scam_does_not_force(fake_store: FakeStore) -> None:
    fake_store.view = make_view(
        risk="scam_or_phishing", triage={"answers": {"risk": {"confidence": 0.5}}}
    )
    out = await policy({"item_id": "i1", "niche": "generic", "decision": DECISION})
    assert out["decision"]["autonomy"] == "ask"


@pytest.mark.parametrize(("conf", "expected"), [(0.8, "suggest"), (0.6, "ask"), (0.5, "ask")])
def test_scam_bands_never_auto(conf: float | None, expected: str) -> None:
    niche = get_registry().get("tech_stack")
    assert niche is not None
    auto = niche.model_copy(update={"autonomy": "auto", "auto_actions": ["archive"]})
    decision = DecisionOut.model_validate(DECISION)
    triage = {"answers": {"risk": {"confidence": conf}}}
    scam = is_scam("scam_or_phishing", triage)
    suspect = scam_suspected("scam_or_phishing", triage)
    assert choose_autonomy(auto, decision, scam=scam, suspect=suspect, expert=False) == expected


def test_none_confidence_counts_as_scam() -> None:
    assert is_scam("scam_or_phishing", {"answers": {"risk": {}}})


async def test_niche_autonomy_is_kept(fake_store: FakeStore) -> None:
    out = await policy({"item_id": "i1", "niche": "tech_stack", "decision": DECISION})
    assert out["decision"]["autonomy"] == "suggest"
    assert out["decision"]["niche_version"] == 1
