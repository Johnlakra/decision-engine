"""Feedback export for Laya fine-tuning and evals (FR-80)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.db.session import get_session
from app.feedback.export import ExportFormat, iter_export
from app.security.api_keys import Principal

router = APIRouter(prefix="/feedback", tags=["feedback"])

NDJSON = "application/x-ndjson"
EXAMPLE_LINE = (
    '{"state":"Pay the water bill","questions":{"needs_decision":{"options":["yes","no"]}},'
    '"gold":{"answers":{"needs_decision":{"yes":0.9,"no":0.1}}}}\n'
)

Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[Principal, Depends(require_scope("admin"))]


@router.get(
    "/export",
    summary="Export human decisions as JSONL",
    operation_id="export_feedback",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "One JSON object per line (laya_train: gold, laya_eval: expected)",
            "content": {NDJSON: {"example": EXAMPLE_LINE, "schema": {"type": "string"}}},
        },
        403: {"description": "API key lacks the admin scope"},
    },
)
async def export_feedback(
    principal: Admin,
    session: Session,
    niche: Annotated[str | None, Query(max_length=100)] = None,
    format: Annotated[ExportFormat, Query()] = "laya_train",  # noqa: A002 - public query name
    since: Annotated[datetime | None, Query()] = None,
) -> StreamingResponse:
    lines = iter_export(
        session, tenant_id=principal.tenant_id, niche=niche, fmt=format, since=since
    )
    return StreamingResponse(lines, media_type=NDJSON)
