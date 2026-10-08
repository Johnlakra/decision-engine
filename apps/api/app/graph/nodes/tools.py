"""tools: run the niche's registered tools in parallel (FR-32, NFR-07)."""

import asyncio
from typing import Any

from app.graph.niche import niche_for
from app.graph.sensitivity import effective_sensitivity
from app.graph.state import GraphState
from app.tools.registry import run_tool


async def tools(state: GraphState) -> dict[str, Any]:
    niche = niche_for(state.get("niche"))
    if not niche.tools:
        return {"tool_results": {}}
    sensitivity = effective_sensitivity(state.get("sensitivity", "private"), niche)
    extracted = state.get("extracted", {})
    results = await asyncio.gather(
        *(run_tool(name, extracted, sensitivity=sensitivity) for name in niche.tools)
    )
    return {
        "tool_results": {
            name: result.model_dump(mode="json")
            for name, result in zip(niche.tools, results, strict=True)
            if result is not None
        }
    }
