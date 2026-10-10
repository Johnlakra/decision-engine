"""``POST /v1/decide``: synchronous Laya answers, optionally a niche decision (FR-35, FR-96).

Persists nothing about the request itself (no item, no decision, no checkpoint).
"""

import asyncio
import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import require_scope
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.graph import oneshot
from app.llm.errors import LLMUnavailable, NoPrivateProvider
from app.schemas.triage import Answer, ShadowRecord
from app.security.api_keys import Principal
from app.triage import service as triage_service

router = APIRouter(prefix="/decide", tags=["decide"])

PROBLEM_BASE = "https://decision-engine/problems/"
MAX_STATE_CHARS = 20_000
Caller = Annotated[Principal, Depends(require_scope("decide"))]


class DecideIn(BaseModel):
    state: Annotated[str, Field(max_length=MAX_STATE_CHARS)] | dict[str, Any] | list[Any]
    questions: dict[str, Any] = Field(default_factory=dict)
    niche: str | None = Field(default=None, max_length=100)
    explain: bool = False
    language: str = Field(default="en", max_length=10)
    sensitivity: Literal["public", "private"] = "public"

    @field_validator("state")
    @classmethod
    def _state_size(cls, value: Any) -> Any:
        """Cap structured state before it is serialized into a prompt (NFR-05)."""
        if not isinstance(value, str):
            size = len(json.dumps(value, ensure_ascii=False))
            if size > MAX_STATE_CHARS:
                raise ValueError(f"state exceeds {MAX_STATE_CHARS} characters when serialized")
        return value


class DecideOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "answers": {
                        "needs_decision": {
                            "type": "choice",
                            "choice": "yes",
                            "probabilities": {"yes": 0.93, "no": 0.07},
                            "confidence": 0.93,
                            "source": "laya",
                        }
                    },
                    "model": "laya",
                    "fallback": False,
                }
            ]
        }
    )

    answers: dict[str, Answer]
    model: str | None = None
    fallback: bool
    decision: dict[str, Any] | None = None
    explanation: str | None = None
    shadow: ShadowRecord | None = None  # Laya output in shadow mode; never the answer


@router.post(
    "",
    response_model=DecideOut,
    response_model_exclude_none=False,
    summary="Synchronous decision",
    operation_id="decide_sync",
    responses={
        422: {"description": "Invalid questions, unknown or disabled niche"},
        503: {"description": "No model could answer, or private with no private_ok provider"},
        504: {"description": "Timed out after DECIDE_TIMEOUT_SECONDS"},
    },
)
async def decide(body: DecideIn, principal: Caller) -> DecideOut:
    timeout = get_settings().decide_timeout_seconds
    try:
        async with asyncio.timeout(timeout):
            result = await oneshot.decide_oneshot(
                laya=triage_service.get_laya_client(),
                tenant_id=str(principal.tenant_id),
                state=body.state,
                questions=body.questions,
                niche=body.niche,
                explain=body.explain,
                language=body.language,
                sensitivity=body.sensitivity,
            )
    except oneshot.InvalidRequest as exc:
        raise ProblemError(422, "Validation failed", str(exc)) from exc
    except NoPrivateProvider as exc:
        raise ProblemError(
            503,
            "No private provider",
            "This request is private and no private_ok model provider is available",
            type=PROBLEM_BASE + "no-private-provider",
        ) from exc
    except LLMUnavailable as exc:
        raise ProblemError(
            503,
            "Model unavailable",
            "No model could answer right now; retry later",
            type=PROBLEM_BASE + "llm-unavailable",
        ) from exc
    except TimeoutError as exc:
        raise ProblemError(504, "Decision timed out", f"No answer within {timeout:g} s") from exc
    return DecideOut(
        answers=result.answers,
        model=result.model,
        fallback=result.fallback,
        decision=result.decision,
        explanation=result.explanation,
        shadow=result.shadow,
    )
