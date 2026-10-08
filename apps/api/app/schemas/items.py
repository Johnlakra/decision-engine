"""Public item shape (C1): mirrors decision_item.schema.json, never exposes raw or hints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import Decision, Item
from app.schemas.content import NormalisedContent


class LastDecision(BaseModel):
    verdict: str
    option: str | None = None
    decided_by: str
    decided_at: datetime


class DecisionItemOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    source: str
    source_ref: str
    received_at: datetime
    status: str
    language: str | None = None
    sensitivity: str
    content: NormalisedContent | None = None
    niche: str | None = None
    urgency: int | None = None
    risk: str | None = None
    deadline_at: datetime | None = None
    related_to: uuid.UUID | None = None
    triage: dict[str, Any] | None = None
    decision: dict[str, Any] | None = None
    last_decision: LastDecision | None = None
    created_at: datetime
    updated_at: datetime


def item_to_public(item: Item, last_decision: Decision | None) -> DecisionItemOut:
    """Build the public view. ``raw``, ``hints`` and ``callback_url`` are never copied."""
    return DecisionItemOut(
        id=item.id,
        tenant_id=item.tenant_id,
        source=item.source,
        source_ref=item.source_ref,
        received_at=item.received_at,
        status=item.status,
        language=item.language,
        sensitivity=item.sensitivity,
        content=NormalisedContent.model_validate(item.content) if item.content else None,
        niche=item.niche,
        urgency=item.urgency,
        risk=item.risk,
        deadline_at=item.deadline_at,
        related_to=item.related_to,
        triage=item.triage,
        decision=item.decision,
        last_decision=(
            None
            if last_decision is None
            else LastDecision(
                verdict=last_decision.verdict,
                option=last_decision.option,
                decided_by=last_decision.decided_by,
                decided_at=last_decision.created_at,
            )
        ),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
