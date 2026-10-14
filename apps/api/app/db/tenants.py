"""The single-tenant default used by CLI loaders and the Telegram bot (MVP: one tenant)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant

DEFAULT_TENANT = "default"


async def ensure_default_tenant(session: AsyncSession) -> uuid.UUID:
    """The default tenant's id, created on first use. Caller commits."""
    tenant = await session.scalar(select(Tenant).where(Tenant.name == DEFAULT_TENANT).limit(1))
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT)
        session.add(tenant)
        await session.flush()
    return tenant.id
