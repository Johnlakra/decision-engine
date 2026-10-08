"""Graph state (C7, ADR 0003): ids and derived data only, JSON-native values.

Item ``raw``, ``content``, ``hints`` and bodies are NEVER stored here; nodes read them from the DB.
"""

from typing import Any, Literal, TypedDict

Route = Literal["decide", "informational", "discarded"]


class GraphState(TypedDict, total=False):
    item_id: str
    tenant_id: str
    niche: str
    niche_version: int
    sensitivity: Literal["public", "private"]
    language: str
    route: Route
    extracted: dict[str, Any]
    tool_results: dict[str, dict[str, Any]]
    decision: dict[str, Any] | None
    verdict: dict[str, Any] | None
    actions_done: list[dict[str, Any]]
