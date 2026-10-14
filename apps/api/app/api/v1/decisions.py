"""Human verdict on a waiting item: ``POST /v1/items/{id}/decision`` (FR-33, FR-34, FR-54).

Resumes the item's LangGraph thread; ``approve`` and ``edit`` run the allowed actions inline.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.errors import ProblemError
from app.db.session import get_session
from app.graph import run
from app.graph.errors import InvalidDecision, ItemBusy, ItemNotFound, NotAwaitingApproval
from app.models.enums import Verdict
from app.niches.overrides import sync_registry
from app.schemas.decision import DecisionIn
from app.security.api_keys import Principal

router = APIRouter(prefix="/items", tags=["items"])

PROBLEM_BASE = "https://decision-engine/problems/"
Writer = Annotated[Principal, Depends(require_scope("items:write"))]


class DecisionResult(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "done"}]})

    status: Literal["done", "rejected", "snoozed", "acting"]


def _status_for(verdict: Verdict, item_status: str) -> str:
    """Reject and snooze report the verdict; approve and edit report where the item ended."""
    if verdict == Verdict.REJECT:
        return "rejected"
    if verdict == Verdict.SNOOZE:
        return "snoozed"
    return item_status


def _require_future_snooze(body: DecisionIn) -> None:
    """422 for a snooze time that has already passed (only here, never on graph replay)."""
    until = body.snooze_until
    if body.verdict != Verdict.SNOOZE or until is None:
        return
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if until <= datetime.now(UTC):
        raise ProblemError(422, "Validation failed", "snooze_until must be in the future")


@router.post(
    "/{item_id}/decision",
    response_model=DecisionResult,
    summary="Approve, reject, edit or snooze a waiting decision",
    operation_id="decide_item",
    responses={
        404: {"description": "No such item for this tenant"},
        409: {"description": "Not awaiting approval, or another request holds the item"},
        422: {"description": "Option is not one of the decision's options, or bad snooze time"},
    },
)
async def submit_decision(
    item_id: uuid.UUID,
    body: DecisionIn,
    principal: Writer,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DecisionResult:
    _require_future_snooze(body)
    await sync_registry(session)  # DB niche overrides (ADR 0009)
    try:
        outcome = await run.resume_item(item_id, principal.tenant_id, body)
    except ItemNotFound as exc:
        raise ProblemError(404, "Not Found", "Item not found") from exc
    except NotAwaitingApproval as exc:
        raise ProblemError(
            409, "Not awaiting approval", str(exc), type=PROBLEM_BASE + "not-awaiting-approval"
        ) from exc
    except ItemBusy as exc:
        raise ProblemError(
            409,
            "Item busy",
            "Another request is processing this item",
            type=PROBLEM_BASE + "item-busy",
        ) from exc
    except InvalidDecision as exc:
        raise ProblemError(422, "Validation failed", str(exc)) from exc
    return DecisionResult.model_validate({"status": _status_for(body.verdict, outcome.status)})
