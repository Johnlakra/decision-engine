"""Public item shape (C1): mirrors decision_item.schema.json, never exposes raw or hints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import Decision, Item
from app.schemas.content import NormalisedContent


class LastDecision(BaseModel):
    verdict: str
    option: str | None = None
    decided_by: str
    decided_at: datetime


class DecisionItemOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",
                    "tenant_id": "0192f0c2-0000-7000-8000-000000000001",
                    "source": "manual",
                    "source_ref": "bill-2026-10",
                    "received_at": "2026-10-09T08:30:00Z",
                    "status": "awaiting_approval",
                    "language": "en",
                    "sensitivity": "public",
                    "niche": "generic",
                    "urgency": 2,
                    "risk": "normal",
                    "created_at": "2026-10-09T08:30:00Z",
                    "updated_at": "2026-10-09T08:30:05Z",
                }
            ]
        }
    )

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
