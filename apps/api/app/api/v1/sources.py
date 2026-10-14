"""Sources: list, add RSS or Google News, enable or disable (FR-90; ADR 0010)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.connectors.poll import FEED_SOURCE
from app.core.errors import ProblemError
from app.core.ids import new_id
from app.core.time import utcnow
from app.db.session import get_session
from app.models import Item, Source
from app.schemas.sources import SourceIn, SourceList, SourceOut, SourcePatch
from app.security.api_keys import Principal

router = APIRouter(prefix="/sources", tags=["sources"])

Reader = Annotated[Principal, Depends(require_scope("items:read"))]
Admin = Annotated[Principal, Depends(require_scope("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]
MAX_SOURCES = 500
FEED_SENSITIVITY = "public"  # feeds are public text (ADR 0005); same as the catalog loader


async def _items_today(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    """Feed items created since 00:00 UTC, by feed slug (the poller stores it as raw.feed)."""
    day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    feed = Item.raw["feed"].astext
    stmt = (
        select(feed, func.count(Item.id))
        .where(
            Item.tenant_id == tenant_id, Item.source == FEED_SOURCE, Item.created_at >= day_start
        )
        .group_by(feed)
    )
    return {slug: int(count) for slug, count in (await session.execute(stmt)).all() if slug}


def _out(row: Source, items_today: int) -> SourceOut:
    return SourceOut(
        id=row.id,
        type=row.type,
        name=row.name,
        slug=row.slug,
        enabled=row.enabled,
        niche_hint=row.niche_hint,
        last_polled_at=row.last_polled_at,
        error_count=row.error_count,
        items_today=items_today,
    )


@router.get(
    "",
    response_model=SourceList,
    summary="List sources",
    operation_id="list_sources",
)
async def list_sources(principal: Reader, session: Session) -> SourceList:
    stmt = (
        select(Source)
        .where(Source.tenant_id == principal.tenant_id)
        .order_by(Source.name, Source.id)
        .limit(MAX_SOURCES)
    )
    rows = (await session.execute(stmt)).scalars().all()
    counts = await _items_today(session, principal.tenant_id)
    return SourceList(data=[_out(r, counts.get(r.slug, 0)) for r in rows])


@router.post(
    "",
    response_model=SourceOut,
    status_code=201,
    summary="Add an RSS or Google News source",
    operation_id="create_source",
    responses={
        403: {"description": "API key lacks the admin scope"},
        409: {"description": "A source with this slug already exists"},
        422: {"description": "Unsupported type, bad slug, or a config that is not an https feed"},
    },
)
async def create_source(body: SourceIn, principal: Admin, session: Session) -> SourceOut:
    stmt = (
        insert(Source)
        .values(
            id=new_id(),
            tenant_id=principal.tenant_id,
            type=body.type,
            name=body.name,
            slug=body.slug,
            config=body.config,
            niche_hint=body.niche_hint,
            sensitivity=FEED_SENSITIVITY,
            enabled=True,
        )
        .on_conflict_do_nothing(index_elements=[Source.tenant_id, Source.slug])
        .returning(Source.id)
    )
    new_source_id = (await session.execute(stmt)).scalar_one_or_none()
    if new_source_id is None:
        raise ProblemError(409, "Slug already used", f"A source with slug {body.slug!r} exists")
    row = await session.get(Source, new_source_id, populate_existing=True)
    if row is None:  # pragma: no cover - the insert above guarantees the row
        raise RuntimeError("source row missing after insert")
    await session.commit()
    return _out(row, 0)


@router.patch(
    "/{source_id}",
    response_model=SourceOut,
    summary="Enable or disable a source",
    operation_id="patch_source",
    responses={
        403: {"description": "API key lacks the admin scope"},
        404: {"description": "No such source for this tenant"},
        422: {"description": "Only 'enabled' (a boolean) may be sent"},
    },
)
async def patch_source(
    source_id: uuid.UUID, body: SourcePatch, principal: Admin, session: Session
) -> SourceOut:
    row = (
        await session.execute(
            select(Source)
            .where(Source.id == source_id, Source.tenant_id == principal.tenant_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ProblemError(404, "Not found", "No such source")
    if row.enabled != body.enabled:
        row.enabled = body.enabled  # only this column: cursor and error_count stay as they are
        await session.commit()
    counts = await _items_today(session, principal.tenant_id)
    return _out(row, counts.get(row.slug, 0))
