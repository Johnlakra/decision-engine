"""Decision schemas: LLM output, stored decision and the human verdict (C1, FR-33, FR-34)."""

from datetime import datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import Verdict

MAX_OPTIONS = 5
MIN_OPTIONS = 2


class ActionSpec(BaseModel):
    type: str
    params: dict[str, Any] = Field(default_factory=dict)


class Option(BaseModel):
    id: str = Field(pattern=r"^[A-E]$")
    label: str = Field(max_length=300)
    actions: list[ActionSpec] = Field(default_factory=list)


class Evidence(BaseModel):
    kind: Literal["field", "tool"]
    ref: str
    as_of: str | None = None


class DecisionOut(BaseModel):
    """What the niche LLM must return (used as the gateway JSON schema)."""

    options: list[Option] = Field(min_length=MIN_OPTIONS, max_length=MAX_OPTIONS)
    recommended: str
    rationale: str = Field(max_length=600)
    evidence: list[Evidence] = Field(default_factory=list)
    deadline: datetime | None = None
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("option ids must be unique")
        if self.recommended not in ids:
            raise ValueError("recommended must be one of the option ids")
        return self


class StoredDecision(DecisionOut):
    """``items.decision``: the LLM output plus policy fields."""

    autonomy: Literal["suggest", "ask", "auto"]
    needs_expert: bool = False
    warnings: list[str] = Field(default_factory=list)
    model: str | None = None
    niche_version: int
    ready_at: datetime | None = None


class DecisionIn(BaseModel):
    """Body of ``POST /v1/items/{id}/decision`` (API.md).

    The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``): the
    graph re-validates this model on a resume replay, long after the time may have passed.
    """

    verdict: Verdict
    option: str | None = None
    edits: dict[str, Any] | None = None
    snooze_until: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _snooze_needs_time(self) -> Self:
        if self.verdict != Verdict.SNOOZE:
            return self
        if self.snooze_until is None:
            raise ValueError("snooze_until is required for snooze")
        return self
