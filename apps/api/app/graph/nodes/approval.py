"""approval: wait for the human verdict with ``interrupt()`` or auto-approve (FR-33, FR-34).

Code before ``interrupt()`` re-runs when the thread resumes, so every pre-interrupt write is
guarded by the current item status (ADR 0003 decision 6). No ``try/except`` wraps ``interrupt()``.
"""

from typing import Any

from langgraph.types import interrupt

from app.graph import store_approval
from app.graph.niche import niche_for
from app.graph.nodes.policy import auto_allowed
from app.graph.state import GraphState
from app.models.enums import DecidedBy, Verdict
from app.schemas.decision import DecisionIn, DecisionOut


def _auto_ok(state: GraphState) -> bool:
    """Auto only when the stored autonomy says so AND the niche allow-list agrees (CLAUDE.md)."""
    decision = state.get("decision") or {}
    if decision.get("autonomy") != "auto" or decision.get("needs_expert"):
        return False
    niche = niche_for(state.get("niche"))
    return niche.autonomy == "auto" and auto_allowed(niche, DecisionOut.model_validate(decision))


async def approval(state: GraphState) -> dict[str, Any]:
    item_id = state["item_id"]
    auto = _auto_ok(state)
    ready = await store_approval.mark_ready(item_id, announce=not auto)
    if auto:
        body = DecisionIn(
            verdict=Verdict.APPROVE, option=(state.get("decision") or {})["recommended"]
        )
        return {
            "verdict": await store_approval.record_verdict(item_id, body, decided_by=DecidedBy.AUTO)
        }
    resume = interrupt({"item_id": item_id, "decision": ready or state.get("decision")})
    body = DecisionIn.model_validate(resume)
    return {
        "verdict": await store_approval.record_verdict(item_id, body, decided_by=DecidedBy.HUMAN)
    }
