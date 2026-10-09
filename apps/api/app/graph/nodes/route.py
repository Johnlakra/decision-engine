"""route: pick the niche subgraph and decide / informational (FR-30, FR-24)."""

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.graph import store
from app.graph.state import GraphState, Route
from app.niches.models import NicheConfig, Triage
from app.niches.registry import FALLBACK_NICHE, NicheRegistry, get_registry
from app.schemas.triage import Answer, TriageRecord

log = logging.getLogger(__name__)

NO_DECISION_CHOICE = "B"  # needs_decision: A = yes, B = no
SELF_VOUCHING_SOURCES = frozenset({"hint", "human"})  # exempt from the gate
UNSCORED_OK_SOURCES = frozenset({"llm_fallback"})  # gated only when it reports a confidence


@dataclass(frozen=True)
class RouteChoice:
    route: Route
    niche: str


def _parse(triage: dict[str, Any] | None) -> TriageRecord | None:
    if not triage:
        return None
    try:
        return TriageRecord.model_validate(triage)
    except ValidationError:
        log.warning("triage record invalid, routing to generic")
        return None


def _confident(answer: Answer, threshold: float) -> bool:
    if answer.source in SELF_VOUCHING_SOURCES:
        return True
    if answer.confidence is None:
        return answer.source in UNSCORED_OK_SOURCES
    return answer.confidence >= threshold


def _accepted_niche(record: TriageRecord | None, registry: NicheRegistry) -> NicheConfig | None:
    answer = record.answers.get("niche") if record else None
    if answer is None or not answer.choice:
        return None
    niche = registry.get(answer.choice)
    if niche is None or not niche.enabled:
        return None
    return niche if _confident(answer, niche.triage.min_confidence) else None


def choose_route(triage: dict[str, Any] | None, registry: NicheRegistry) -> RouteChoice:
    record = _parse(triage)
    niche = _accepted_niche(record, registry)
    name = niche.name if niche else FALLBACK_NICHE
    threshold = niche.triage.min_confidence if niche else Triage().min_confidence
    needs = record.answers.get("needs_decision") if record else None
    if needs is not None and needs.choice == NO_DECISION_CHOICE and _confident(needs, threshold):
        return RouteChoice("informational", name)
    return RouteChoice("decide", name)


async def route(state: GraphState) -> dict[str, Any]:
    view = await store.load_item_view(state["item_id"])
    choice = choose_route(view.triage, get_registry())
    niche = get_registry().get(choice.niche)
    await store.apply_route(
        state["item_id"], niche=choice.niche, informational=choice.route == "informational"
    )
    return {
        "route": choice.route,
        "niche": choice.niche,
        "niche_version": niche.version if niche else 1,
    }
