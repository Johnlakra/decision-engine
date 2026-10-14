"""Items router: ingest, bulk ingest, list, get (FR-01, FR-02, FR-03, FR-06, FR-07)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.config import get_settings
from app.core.errors import PROBLEM_JSON, ProblemError
from app.core.time import utcnow
from app.db.session import get_session
from app.ingest.service import (
    find_existing,
    ingest_one,
    lock_tenant_quota,
    remaining_quota,
    seconds_until_utc_midnight,
)
from app.models import ActionLog, Decision, Item
from app.schemas.ingest import MAX_BULK, BulkRow, IngestItemIn, IngestResult
from app.schemas.items import DecisionItemOut, item_to_public
from app.security.api_keys import Principal

ACTIVITY_LIMIT = 50

router = APIRouter(prefix="/items", tags=["items"])

DAILY_CAP_TYPE = "https://decision-engine/problems/daily-item-cap"
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
CAP_ROW_ERROR = "daily item cap reached"

Session = Annotated[AsyncSession, Depends(get_session)]
Writer = Annotated[Principal, Depends(require_scope("items:write"))]
Reader = Annotated[Principal, Depends(require_scope("items:read"))]


class BulkOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "results": [
                        {"index": 0, "id": "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e", "status": "new"},
                        {"index": 1, "error": "source: Field required"},
                    ]
                }
            ]
        }
    )

    results: list[BulkRow]


class ItemPage(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"data": [], "next_cursor": None}]})

    data: list[DecisionItemOut]
    next_cursor: str | None = None


def _cap_response(request: Request) -> JSONResponse:
    retry_after = seconds_until_utc_midnight(utcnow())
    body = {
        "type": DAILY_CAP_TYPE,
        "title": "Daily item cap reached",
        "status": 429,
        "detail": "This tenant reached its daily item limit; it resets at 00:00 UTC",
        "instance": request.url.path,
    }
    return JSONResponse(
        body,
        status_code=429,
        media_type=PROBLEM_JSON,
        headers={"Retry-After": str(retry_after)},
    )


@router.post(
    "",
    response_model=IngestResult,
    status_code=202,
    summary="Ingest one item",
    operation_id="create_item",
    responses={
        200: {
            "model": IngestResult,
            "description": "Repeat of (source, source_ref): the existing item",
        },
        429: {"description": "Rate limit or daily item cap; see Retry-After"},
    },
)
async def create_item(
    body: IngestItemIn,
    request: Request,
    response: Response,
    principal: Writer,
    session: Session,
) -> IngestResult | JSONResponse:
    """Store the payload untouched and queue it for the pipeline. Idempotent."""
    await lock_tenant_quota(session, principal.tenant_id)  # count-and-insert is atomic
    existing = await find_existing(session, principal.tenant_id, body.source, body.source_ref)
    if existing is not None:  # idempotent repeat is never capped (FR-07 over FR-02)
        response.status_code = 200
        return IngestResult(id=str(existing.id), status=existing.status)
    cap = get_settings().items_per_day
    if await remaining_quota(session, principal.tenant_id, cap) <= 0:
        return _cap_response(request)
    item, created = await ingest_one(session, principal.tenant_id, body)
    await session.commit()
    response.status_code = 202 if created else 200
    return IngestResult(id=str(item.id), status=item.status)


def _row_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    return f"{'.'.join(str(p) for p in first['loc'])}: {first['msg']}"


@router.post(
    "/bulk",
    response_model=BulkOut,
    status_code=207,
    summary="Ingest up to 500 items",
    operation_id="create_items_bulk",
    responses={429: {"description": "Daily item cap; see Retry-After"}},
)
async def create_items_bulk(
    payload: dict[str, Any],
    request: Request,
    principal: Writer,
    session: Session,
) -> BulkOut | JSONResponse:
    """One savepoint per row; a bad row never fails the others."""
    rows = payload.get("items")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_BULK:
        raise ProblemError(
            422, "Validation failed", f"'items' must be a list of 1 to {MAX_BULK} objects"
        )
    await lock_tenant_quota(session, principal.tenant_id)
    remaining = await remaining_quota(session, principal.tenant_id, get_settings().items_per_day)
    results: list[BulkRow] = []
    for index, raw_row in enumerate(rows):
        row, created = await _ingest_row(session, principal.tenant_id, index, raw_row, remaining)
        results.append(row)
        remaining -= int(created)  # only new rows spend quota; repeats are free
    refused = any(r.error == CAP_ROW_ERROR for r in results)
    if refused and all(r.id is None for r in results):  # nothing stored or found: plain 429
        return _cap_response(request)
    await session.commit()
    return BulkOut(results=results)


async def _ingest_row(
    session: AsyncSession, tenant_id: uuid.UUID, index: int, raw_row: Any, remaining: int
) -> tuple[BulkRow, bool]:
    """Returns the row result and whether a new item was stored (spends quota)."""
    try:
        body = IngestItemIn.model_validate(raw_row)
    except ValidationError as exc:
        return BulkRow(index=index, error=_row_error(exc)), False
    if remaining <= 0:  # out of quota: only already-stored rows pass; new ones are refused
        existing = await find_existing(session, tenant_id, body.source, body.source_ref)
        if existing is None:
            return BulkRow(index=index, error=CAP_ROW_ERROR), False
        return BulkRow(index=index, id=str(existing.id), status=existing.status), False
    try:
        async with session.begin_nested():
            item, created = await ingest_one(session, tenant_id, body)
    except Exception:  # noqa: BLE001 - one bad row must not fail the batch
        return BulkRow(index=index, error="could not store item"), False
    return BulkRow(index=index, id=str(item.id), status=item.status), created


def _parse_cursor(cursor: str | None) -> uuid.UUID | None:
    if cursor is None:
        return None
    try:
        return uuid.UUID(cursor)
    except ValueError as exc:
        raise ProblemError(422, "Validation failed", "cursor is not valid") from exc


async def _latest_decisions(
    session: AsyncSession, tenant_id: uuid.UUID, item_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Decision]:
    if not item_ids:
        return {}
    stmt = (
        select(Decision)
        .where(
            Decision.tenant_id == tenant_id,
            Decision.item_id.in_(item_ids),
            Decision.undone_at.is_(None),
        )
        .order_by(Decision.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.item_id: row for row in rows}  # later (newer) ids overwrite earlier ones


@router.get(
    "",
    response_model=ItemPage,
    summary="List items",
    operation_id="list_items",
)
async def list_items(
    principal: Reader,
    session: Session,
    status: str | None = None,
    niche: str | None = None,
    source: str | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ItemPage:
    """Newest first. `cursor` is the `next_cursor` of the previous page."""
    stmt = select(Item).where(Item.tenant_id == principal.tenant_id)
    if status:
        stmt = stmt.where(Item.status == status)
    if niche:
        stmt = stmt.where(Item.niche == niche)
    if source:
        stmt = stmt.where(Item.source == source)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Item.content["title"].astext.ilike(f"%{escaped}%", escape="\\"))
    after = _parse_cursor(cursor)
    if after is not None:
        stmt = stmt.where(Item.id < after)
    stmt = stmt.order_by(Item.id.desc()).limit(limit + 1)
    items = list((await session.execute(stmt)).scalars().all())
    has_more = len(items) > limit
    page = items[:limit]
    decisions = await _latest_decisions(session, principal.tenant_id, [i.id for i in page])
    return ItemPage(
        data=[item_to_public(i, decisions.get(i.id)) for i in page],
        next_cursor=str(page[-1].id) if has_more else None,
    )


@router.get(
    "/{item_id}",
    response_model=DecisionItemOut,
    summary="Get one item",
    operation_id="get_item",
    responses={404: {"description": "No such item for this tenant"}},
)
async def get_item(item_id: uuid.UUID, principal: Reader, session: Session) -> DecisionItemOut:
    item = (
        await session.execute(
            select(Item).where(Item.id == item_id, Item.tenant_id == principal.tenant_id)
        )
    ).scalar_one_or_none()
    if item is None:
        raise ProblemError(404, "Not found", "Item not found")
    decisions = await _latest_decisions(session, principal.tenant_id, [item.id])
    return item_to_public(item, decisions.get(item.id))


class ActivityEntry(BaseModel):
    """One executed action on an item. Params and results are not shown: they can hold URLs."""

    action: str
    status: str
    created_at: datetime
    reversible: bool
    undone_at: datetime | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "data": [
                        {
                            "action": "archive",
                            "status": "done",
                            "created_at": "2026-10-09T09:00:00Z",
                            "reversible": False,
                            "undone_at": None,
                        }
                    ]
                }
            ]
        }
    )

    data: list[ActivityEntry]


@router.get(
    "/{item_id}/activity",
    response_model=ActivityOut,
    summary="Actions taken on one item, newest first",
    operation_id="get_item_activity",
    responses={404: {"description": "No such item for this tenant"}},
)
async def get_item_activity(item_id: uuid.UUID, principal: Reader, session: Session) -> ActivityOut:
    owned = await session.scalar(
        select(Item.id).where(Item.id == item_id, Item.tenant_id == principal.tenant_id)
    )
    if owned is None:
        raise ProblemError(404, "Not found", "Item not found")
    stmt = (
        select(ActionLog)
        .where(ActionLog.tenant_id == principal.tenant_id, ActionLog.item_id == item_id)
        .order_by(ActionLog.created_at.desc(), ActionLog.id.desc())
        .limit(ACTIVITY_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return ActivityOut(
        data=[
            ActivityEntry(
                action=row.action,
                status=row.status,
                created_at=row.created_at,
                reversible=row.reversible,
                undone_at=row.undone_at,
            )
            for row in rows
        ]
    )
