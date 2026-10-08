"""Policy (FR-25, FR-34)."""

from typing import Any

from app.graph.nodes.policy import SCAM_WARNING, policy
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


async def test_niche_autonomy_is_kept(fake_store: FakeStore) -> None:
    out = await policy({"item_id": "i1", "niche": "tech_stack", "decision": DECISION})
    assert out["decision"]["autonomy"] == "suggest"
    assert out["decision"]["niche_version"] == 1
