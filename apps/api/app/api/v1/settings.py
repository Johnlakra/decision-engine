"""Tenant settings: GET and PUT /v1/settings (FR-43). Reads: items:read; writes: admin."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.errors import ProblemError
from app.db.session import get_session
from app.models import TenantSettings
from app.niches.overrides import sync_registry
from app.niches.registry import get_registry
from app.schemas import laya_settings
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
    responses={
        422: {
            "description": (
                "A setting is out of range, a Laya mode names an unknown niche (unknown_niche), "
                "or a change to 'on' was asked for (laya_mode_gated)"
            )
        }
    },
)
async def write_settings(body: SettingsIn, principal: Admin, session: Session) -> SettingsOut:
    registry = get_registry()
    await sync_registry(session, registry)  # DB-only niches count as known
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
    _check_laya_modes(body, row.settings, {n.name for n in registry.all()})
    # Keep keys this form does not own (e.g. the notifier's digest_sent_on marker).
    updated = laya_settings.merge_settings(row.settings, body)
    row.settings = updated
    await session.commit()
    return settings_out(updated)


def _check_laya_modes(body: SettingsIn, stored: dict[str, Any], known: set[str]) -> None:
    """422 for unknown niches (first) or a change to 'on' (ADR 0008)."""
    unknown = laya_settings.unknown_niche_errors(body, known)
    gated = laya_settings.gated_errors(body, stored)
    if unknown:
        raise ProblemError(
            422, "Validation failed", "Request validation failed", errors=unknown + gated
        )
    if gated:
        raise ProblemError(
            422,
            laya_settings.GATED_TITLE,
            laya_settings.GATED_DETAIL,
            type=laya_settings.GATED_TYPE,
            errors=gated,
        )
