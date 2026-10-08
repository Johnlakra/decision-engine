"""Triage records stored in ``items.triage`` (C1, FR-20, FR-21, FR-24)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AnswerSource = Literal["laya", "llm_fallback", "hint", "human"]


class Answer(BaseModel):
    type: Literal["choice", "score", "noul"]
    choice: str | None = None
    score: float | None = None
    level: int | None = None
    noul: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = None
    source: AnswerSource


class ShadowRecord(BaseModel):
    answers: dict[str, Answer] | None = None
    model: str | None = None
    latency_ms: int | None = None
    error: str | None = None


class TriageRecord(BaseModel):
    mode: Literal["off", "shadow", "on"]
    model: str | None = None
    laya_version: str | None = None
    fallback: bool = False
    decided_by: Literal["laya", "llm_fallback", "human"]
    answers: dict[str, Answer] = Field(default_factory=dict)
    questions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    shadow: ShadowRecord | None = None
    latency_ms: int = 0
    error: str | None = None
