"""Pydantic mirror of schemas/niche.schema.json (FR-70)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscardRule(_Strict):
    question: str
    choice: str
    min_confidence: float = Field(ge=0.5, le=1)


class Triage(_Strict):
    min_confidence: float = Field(default=0.75, ge=0, le=1)
    questions: dict[str, dict[str, Any]] = Field(default_factory=dict, max_length=8)
    discard_if: list[DiscardRule] = Field(default_factory=list)


class ExpertReview(_Strict):
    always: bool = False
    when_topics: list[str] = Field(default_factory=list)


class Notify(_Strict):
    urgent_ping: bool = True
    digest: bool = True
    min_urgency_for_ping: int = Field(default=2, ge=0, le=2)


class LlmPrefs(_Strict):
    purpose_decide: str = "decide"
    max_tokens: int = 800
    prefer: list[str] = Field(default_factory=list)


class NicheConfig(_Strict):
    name: str
    label: str
    description: str
    enabled: bool
    version: int = Field(default=1, ge=1)
    languages: list[str] = Field(default_factory=lambda: ["en"])
    sensitivity: Literal["public", "private"] = "public"
    triage: Triage = Field(default_factory=Triage)
    extract: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    prompt: str
    options_hint: list[str] = Field(default_factory=list, max_length=6)
    actions: list[str] = Field(min_length=1)
    autonomy: Literal["suggest", "ask", "auto"]
    auto_actions: list[str] = Field(default_factory=list)
    expert_review: ExpertReview = Field(default_factory=ExpertReview)
    notify: Notify = Field(default_factory=Notify)
    few_shot: int = Field(default=6, ge=0, le=12)
    llm: LlmPrefs = Field(default_factory=LlmPrefs)
    steps: list[str] | None = None
    evals: str | None = None
