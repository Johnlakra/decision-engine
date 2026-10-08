"""load: read the item once and seed the state with ids and derived data only (C7)."""

from typing import Any

from app.graph import store
from app.graph.state import GraphState
from app.niches.registry import FALLBACK_NICHE


async def load(state: GraphState) -> dict[str, Any]:
    view = await store.load_item_view(state["item_id"])
    sensitivity = "private" if view.sensitivity == "private" else "public"
    return {
        "tenant_id": view.tenant_id,
        "sensitivity": sensitivity,
        "language": view.language,
        "niche": view.niche or FALLBACK_NICHE,
        "extracted": {},
        "tool_results": {},
        "decision": None,
        "verdict": None,
        "actions_done": [],
    }
