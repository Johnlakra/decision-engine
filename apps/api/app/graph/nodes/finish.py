"""finish: informational and rejected items become ``done`` (FR-30)."""

from typing import Any

from app.graph import store_approval
from app.graph.state import GraphState


async def finish(state: GraphState) -> dict[str, Any]:
    await store_approval.complete_item(state["item_id"])
    return {}
