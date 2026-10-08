"""act: run the chosen option's actions through the registry (FR-40, FR-41, NFR-07).

Under ``suggest`` autonomy nothing runs. Only actions in the niche allow-list ever run, including
actions a human supplied in ``edits``.
"""

import logging
from typing import Any

from pydantic import ValidationError

from app.graph import store_approval
from app.graph.niche import niche_for
from app.graph.nodes.decide import allowed_actions
from app.graph.state import GraphState
from app.models.enums import Verdict
from app.schemas.decision import ActionSpec

log = logging.getLogger(__name__)

ACTING_VERDICTS = frozenset({Verdict.APPROVE.value, Verdict.EDIT.value})


def chosen_actions(state: GraphState) -> list[dict[str, Any]]:
    decision = state.get("decision") or {}
    verdict = state.get("verdict") or {}
    edits = verdict.get("edits") or {}
    if verdict.get("verdict") == Verdict.EDIT.value and isinstance(edits.get("actions"), list):
        try:
            return [ActionSpec.model_validate(a).model_dump() for a in edits["actions"]]
        except ValidationError:
            log.warning("edited actions invalid item=%s; using the option's", state.get("item_id"))
    option = next(
        (o for o in decision.get("options", []) if o["id"] == verdict.get("option")), None
    )
    return list(option["actions"]) if option else []


async def act(state: GraphState) -> dict[str, Any]:
    verdict = state.get("verdict") or {}
    if verdict.get("verdict") not in ACTING_VERDICTS:
        return {"actions_done": []}
    niche = niche_for(state.get("niche"))
    allowed = allowed_actions(niche)
    specs = [a for a in chosen_actions(state) if a["type"] in allowed]
    run = (state.get("decision") or {}).get("autonomy") != "suggest"
    done = await store_approval.execute_actions(
        state["item_id"], state["tenant_id"], verdict.get("option"), specs, run=run
    )
    return {"actions_done": done}
