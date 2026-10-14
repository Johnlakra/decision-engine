"""DB niche overrides and the fingerprint sync that keeps every process fresh (ADR 0009)."""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.niche import Niche
from app.niches.registry import NicheRegistry, ReloadResult, get_registry

log = logging.getLogger(__name__)

Fingerprint = tuple[int, int, datetime | None]


async def overrides_fingerprint(session: AsyncSession) -> Fingerprint:
    """One indexed aggregate over ``niches``: (row count, sum of versions, newest update)."""
    stmt = select(
        func.count(Niche.id),
        func.coalesce(func.sum(Niche.version), 0),
        func.max(Niche.updated_at),
    )
    count, total, newest = (await session.execute(stmt)).one()
    return int(count), int(total), newest


async def load_overrides(session: AsyncSession) -> dict[str, dict[str, Any]]:
    """name -> complete config. Rows of more than one tenant apply none (fail closed to YAML)."""
    rows = (await session.execute(select(Niche.tenant_id, Niche.name, Niche.config))).all()
    if len({tenant_id for tenant_id, _, _ in rows}) > 1:
        log.error("niche overrides span more than one tenant; applying none (per-tenant: 8.5)")
        return {}
    return {name: dict(config) for _, name, config in rows}


async def reload_registry(session: AsyncSession, registry: NicheRegistry) -> ReloadResult:
    """Re-read YAML and re-apply DB overrides unconditionally. May raise (caller decides)."""
    fingerprint = await overrides_fingerprint(session)  # first, so a racing PUT is seen next time
    overrides = await load_overrides(session)
    result = await asyncio.to_thread(registry.reload, overrides)
    registry.fingerprint = fingerprint
    return result


async def sync_registry(session: AsyncSession, registry: NicheRegistry | None = None) -> bool:
    """Reload when the overrides fingerprint changed. Never raises: errors keep the registry."""
    registry = registry or get_registry()
    try:
        async with session.begin_nested():
            fingerprint = await overrides_fingerprint(session)
            if fingerprint == registry.fingerprint:
                return False
            overrides = await load_overrides(session)
        await asyncio.to_thread(registry.reload, overrides)
        registry.fingerprint = fingerprint
        return True
    except Exception:
        log.exception("niche sync failed; keeping the current registry")
        return False


async def save_override(session: AsyncSession, tenant_id: uuid.UUID, config: dict[str, Any]) -> int:
    """Upsert the tenant's row for ``config["name"]``; the server owns ``version``. No commit."""
    name = str(config["name"])
    insert_stmt = insert(Niche).values(
        tenant_id=tenant_id,
        name=name,
        config={**config, "version": 1},
        version=1,
        enabled=bool(config["enabled"]),
        source="db",
    )
    next_version = Niche.version + 1
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[Niche.tenant_id, Niche.name],
        set_={
            "config": func.jsonb_set(
                insert_stmt.excluded.config,
                text("'{version}'::text[]"),
                func.to_jsonb(next_version),
            ),
            "version": next_version,
            "enabled": insert_stmt.excluded.enabled,
            "source": "db",
            "updated_at": func.now(),
        },
    ).returning(Niche.version)
    return int((await session.execute(stmt)).scalar_one())
