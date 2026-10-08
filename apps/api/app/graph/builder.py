"""Turn the niche config into the one parameterised LangGraph template (FR-30, ADR 0003).

load -> route -> (extract -> tools -> decide -> policy -> approval -> act ->) finish. The niche
YAML picks tools, actions and prompts; it never changes the graph shape in Phase 1.
"""

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from app.graph.errors import UnsupportedSteps
from app.graph.nodes.act import act
from app.graph.nodes.approval import approval
from app.graph.nodes.decide import decide
from app.graph.nodes.extract import extract
from app.graph.nodes.finish import finish
from app.graph.nodes.load import load
from app.graph.nodes.policy import policy
from app.graph.nodes.route import route
from app.graph.nodes.tools import tools
from app.graph.state import GraphState
from app.models.enums import Verdict
from app.niches.registry import NicheRegistry, get_registry

ROUTE_NODE = "route_niche"  # "route" is a state key and cannot be a node name


def reject_custom_steps(registry: NicheRegistry) -> None:
    for niche in registry.all():
        if niche.steps:
            raise UnsupportedSteps(
                f"niche {niche.name!r} declares steps: {niche.steps}; custom steps need a new ADR"
            )


def _after_route(state: GraphState) -> Literal["extract", "finish", "__end__"]:
    match state.get("route"):
        case "decide":
            return "extract"
        case "informational":
            return "finish"
        case _:
            return "__end__"


def _after_approval(state: GraphState) -> Literal["approval", "act"]:
    verdict = (state.get("verdict") or {}).get("verdict")
    return "approval" if verdict == Verdict.SNOOZE.value else "act"


def build_graph(checkpointer: Any, registry: NicheRegistry | None = None) -> Any:
    """Compile the template with ``checkpointer``. Rejects niches that declare ``steps:``."""
    reject_custom_steps(registry or get_registry())
    builder = StateGraph(GraphState)
    for name, node in (
        ("load", load),
        (ROUTE_NODE, route),
        ("extract", extract),
        ("tools", tools),
        ("decide", decide),
        ("policy", policy),
        ("approval", approval),
        ("act", act),
        ("finish", finish),
    ):
        builder.add_node(name, node)
    builder.add_edge(START, "load")
    builder.add_edge("load", ROUTE_NODE)
    builder.add_conditional_edges(ROUTE_NODE, _after_route)
    for upstream, downstream in (
        ("extract", "tools"),
        ("tools", "decide"),
        ("decide", "policy"),
        ("policy", "approval"),
    ):
        builder.add_edge(upstream, downstream)
    builder.add_conditional_edges("approval", _after_approval)
    builder.add_edge("act", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)
