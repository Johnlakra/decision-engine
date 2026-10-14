"""Tenant settings: GET and PUT /v1/settings (FR-43). Reads: items:read; writes: admin."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.db.session import get_session
from app.models import TenantSettings
from app.schemas.settings import SettingsIn, SettingsOut, settings_out
from app.security.api_keys import Principal

router = APIRouter(prefix="/settings", tags=["settings"])

Reader = Annotated[Principal, Depends(require_scope("items:read"))]
Admin = Annotated[Principal, Depends(require_scope("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.get(
    "",
    response_model=SettingsOut,
    summary="Read tenant settings",
    operation_id="get_settings",
)
async def read_settings(principal: Reader, session: Session) -> SettingsOut:
    row = await session.get(TenantSettings, principal.tenant_id)
    return settings_out(row.settings if row is not None else None)


@router.put(
    "",
    response_model=SettingsOut,
    summary="Replace tenant settings",
    operation_id="put_settings",
    responses={422: {"description": "A setting is out of range"}},
)
async def write_settings(body: SettingsIn, principal: Admin, session: Session) -> SettingsOut:
    # Create the row if missing (race-safe), then lock it so a concurrent PUT or the
    # notifier's digest_sent_on write serializes with this one instead of being lost.
    await session.execute(
        insert(TenantSettings)
        .values(tenant_id=principal.tenant_id, settings={})
        .on_conflict_do_nothing(index_elements=[TenantSettings.tenant_id])
    )
    row = await session.scalar(
        select(TenantSettings)
        .where(TenantSettings.tenant_id == principal.tenant_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:  # pragma: no cover - the insert above guarantees the row
        raise RuntimeError("tenant settings row missing after upsert")
    # Keep keys this form does not own (e.g. the notifier's digest_sent_on marker).
    updated = {**row.settings, **body.model_dump()}
    row.settings = updated
    await session.commit()
    return settings_out(updated)
