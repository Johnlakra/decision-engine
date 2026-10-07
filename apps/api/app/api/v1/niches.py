"""Niche admin routes (FR-70, FR-71)."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.api.deps import require_scope
from app.core.errors import ProblemError
from app.niches.registry import MissingGenericNicheError, NicheError, get_registry
from app.security.api_keys import Principal

router = APIRouter(prefix="/niches", tags=["niches"])


class ReloadResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"loaded": ["agriculture", "generic", "inbox", "news_radar", "tech_stack"]}
            ]
        }
    )

    loaded: list[str]
    errors: list[dict[str, str]] = []


def _error_dicts(errors: list[NicheError]) -> list[dict[str, Any]]:
    return [{"file": e.file, "json_pointer": e.json_pointer, "message": e.message} for e in errors]


@router.post(
    "/reload",
    response_model=ReloadResponse,
    summary="Reload niche configs from disk",
    operation_id="reload_niches",
    responses={
        403: {"description": "API key lacks the admin scope"},
        422: {
            "description": "Validation errors; the previous niche set is still served",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Niche validation failed",
                        "status": 422,
                        "detail": "1 niche file(s) are invalid; previous versions stay active",
                        "errors": [
                            {
                                "file": "inbox.yaml",
                                "json_pointer": "/autonomy",
                                "message": "'yolo' is not one of ['ask', 'auto']",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def reload_niches(
    _: Annotated[Principal, Depends(require_scope("admin"))],
) -> ReloadResponse:
    registry = get_registry()
    try:
        result = await asyncio.to_thread(registry.reload)
    except MissingGenericNicheError as exc:
        raise ProblemError(
            422,
            "Niche validation failed",
            str(exc),
            errors=_error_dicts(registry.errors),
        ) from exc
    if result.errors:
        raise ProblemError(
            422,
            "Niche validation failed",
            f"{len(result.errors)} niche problem(s); previous versions stay active",
            errors=_error_dicts(result.errors),
        )
    return ReloadResponse(loaded=result.loaded)
