"""policy: autonomy, expert review and scam handling (FR-25, FR-34)."""

import json
from typing import Any, Literal

from app.graph import store
from app.graph.niche import niche_for
from app.graph.state import GraphState
from app.niches.models import NicheConfig
from app.schemas.decision import DecisionOut, StoredDecision

Autonomy = Literal["suggest", "ask", "auto"]

SCAM_RISK = "scam_or_phishing"
SCAM_MIN_CONFIDENCE = 0.8
SCAM_WARNING = "Possible scam or phishing. Review carefully; automatic actions are disabled."
EXPERT_WARNING = "Expert review recommended before acting."


def is_scam(risk: str | None, triage: dict[str, Any] | None) -> bool:
    if risk != SCAM_RISK:
        return False
    answer = ((triage or {}).get("answers") or {}).get("risk") or {}
    confidence = answer.get("confidence")
    return confidence is None or float(confidence) >= SCAM_MIN_CONFIDENCE


def needs_expert(niche: NicheConfig, haystack: str) -> bool:
    review = niche.expert_review
    if review.always:
        return True
    text = haystack.lower()
    return any(topic.lower() in text for topic in review.when_topics)


def auto_allowed(niche: NicheConfig, decision: DecisionOut) -> bool:
    option = next((o for o in decision.options if o.id == decision.recommended), None)
    if option is None or not option.actions:
        return False
    return all(a.type in niche.auto_actions for a in option.actions)


def choose_autonomy(
    niche: NicheConfig, decision: DecisionOut, *, scam: bool, expert: bool
) -> Autonomy:
    if scam:
        return "suggest"
    if niche.autonomy == "auto" and (expert or not auto_allowed(niche, decision)):
        return "ask"
    return niche.autonomy


def apply_policy(state: GraphState, niche: NicheConfig, view: store.ItemView) -> dict[str, Any]:
    """Autonomy, expert review and scam warning for the decision in ``state`` (no persistence)."""
    out = DecisionOut.model_validate(state["decision"])
    scam = is_scam(view.risk, view.triage)
    haystack = json.dumps(
        [view.content.get("title"), state.get("extracted"), out.rationale], default=str
    )
    expert = needs_expert(niche, haystack)
    warnings = ([SCAM_WARNING] if scam else []) + ([EXPERT_WARNING] if expert else [])
    stored = StoredDecision(
        **out.model_dump(),
        autonomy=choose_autonomy(niche, out, scam=scam, expert=expert),
        needs_expert=expert,
        warnings=warnings,
        niche_version=state.get("niche_version", niche.version),
    )
    return stored.model_dump(mode="json")


async def policy(state: GraphState) -> dict[str, Any]:
    niche = niche_for(state.get("niche"))
    view = await store.load_item_view(state["item_id"])
    dumped = apply_policy(state, niche, view)
    await store.save_decision(state["item_id"], dumped)
    return {"decision": dumped}
