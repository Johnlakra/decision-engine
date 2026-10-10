"""load_corrections filters by the source item's sensitivity in SQL (FR-62, NFR-07, H1)."""

import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.ids import new_id
from app.graph import store
from app.models import Feedback, Item, Tenant

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


async def seed(factory: SessionFactory, tenant: Tenant) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    async with factory() as session:
        for sens in ("private", "public"):
            item_id = new_id()
            ids[sens] = item_id
            session.add(
                Item(
                    id=item_id,
                    tenant_id=tenant.id,
                    source="manual",
                    source_ref=str(item_id),
                    raw={},
                    niche="generic",
                    sensitivity=sens,
                    content={},
                )
            )
        await session.flush()
        for sens, item_id in ids.items():
            session.add(
                Feedback(
                    id=new_id(),
                    tenant_id=tenant.id,
                    item_id=item_id,
                    niche="generic",
                    kind="decision",
                    state_text=f"{sens.upper()}TEXT",
                    gold={"decision": {"verdict": "approve"}},
                )
            )
        await session.commit()
    return ids


async def texts(tenant: Tenant, **kw: str) -> set[str]:
    rows = await store.load_corrections(str(tenant.id), "generic", 10, **kw)
    return {r.state_text for r in rows}


async def test_public_call_excludes_private_rows(
    committed_db: SessionFactory, tenant_committed: Tenant
) -> None:
    await seed(committed_db, tenant_committed)
    assert await texts(tenant_committed, sensitivity="public") == {"PUBLICTEXT"}


async def test_default_is_the_safe_public_filter(
    committed_db: SessionFactory, tenant_committed: Tenant
) -> None:
    await seed(committed_db, tenant_committed)
    assert await texts(tenant_committed) == {"PUBLICTEXT"}


async def test_private_call_sees_both(
    committed_db: SessionFactory, tenant_committed: Tenant
) -> None:
    await seed(committed_db, tenant_committed)
    assert await texts(tenant_committed, sensitivity="private") == {"PRIVATETEXT", "PUBLICTEXT"}


async def test_deleted_item_leaves_no_crash_and_no_row(
    committed_db: SessionFactory, tenant_committed: Tenant
) -> None:
    ids = await seed(committed_db, tenant_committed)
    async with committed_db() as session:
        await session.execute(delete(Item).where(Item.id == ids["public"]))
        await session.commit()
    assert await texts(tenant_committed, sensitivity="public") == set()
    assert await texts(tenant_committed, sensitivity="private") == {"PRIVATETEXT"}
