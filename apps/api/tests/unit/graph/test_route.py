"""Routing table (FR-30, FR-24)."""

from typing import Any

import pytest

from app.graph.nodes.route import choose_route, route
from app.niches.registry import NicheRegistry
from tests.unit.graph.conftest import FakeStore, make_view


def triage(
    niche: str | None = "tech_stack",
    nconf: float | None = 0.9,
    nsrc: str = "laya",
    needs: str = "A",
    needs_conf: float | None = 0.9,
) -> dict[str, Any]:
    answers: dict[str, Any] = {
        "needs_decision": {
            "type": "choice",
            "choice": needs,
            "confidence": needs_conf,
            "source": nsrc,
        },
    }
    if niche:
        answers["niche"] = {"type": "choice", "choice": niche, "confidence": nconf, "source": nsrc}
    return {"mode": "on", "decided_by": "laya", "answers": answers}


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (triage(), ("decide", "tech_stack")),
        (triage(nconf=0.5), ("decide", "generic")),
        (triage(niche="nope"), ("decide", "generic")),
        (triage(niche="inbox"), ("decide", "generic")),  # disabled niche
        (triage(niche=None), ("decide", "generic")),
        (triage(nconf=None, nsrc="llm_fallback"), ("decide", "tech_stack")),
        (triage(nconf=None, nsrc="laya"), ("decide", "generic")),
        (triage(nconf=0.5, nsrc="llm_fallback"), ("decide", "generic")),
        (triage(nsrc="llm_fallback", needs="B", needs_conf=0.4), ("decide", "tech_stack")),
        (triage(nsrc="llm_fallback", needs="B", needs_conf=0.95), ("informational", "tech_stack")),
        (triage(nsrc="hint", needs="B", needs_conf=0.1), ("informational", "tech_stack")),
        (triage(nsrc="human", needs="B", needs_conf=0.1), ("informational", "tech_stack")),
        (triage(needs="B"), ("informational", "tech_stack")),
        (triage(needs="B", needs_conf=0.3), ("decide", "tech_stack")),
        (None, ("decide", "generic")),
        ({"garbage": 1}, ("decide", "generic")),
    ],
)
def test_choose_route(record: Any, expected: tuple[str, str], registry: NicheRegistry) -> None:
    choice = choose_route(record, registry)
    assert (choice.route, choice.niche) == expected


async def test_route_node_applies_status_and_niche(fake_store: FakeStore) -> None:
    fake_store.view = make_view(triage=triage(needs="B"))
    out = await route({"item_id": "i1"})
    assert out["route"] == "informational"
    assert fake_store.route == ("tech_stack", True)
