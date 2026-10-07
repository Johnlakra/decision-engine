"""Insert one demo item and enqueue its process job in one transaction (acceptance A4)."""

import asyncio

from sqlalchemy import select

from app.core.ids import new_id
from app.db.session import session_scope
from app.models.enums import JobKind
from app.models.item import Item
from app.models.tenant import Tenant
from app.workers.queue import enqueue

DEFAULT_TENANT = "default"


async def create_demo_item() -> str:
    async with session_scope() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.name == DEFAULT_TENANT).limit(1))
        if tenant is None:
            tenant = Tenant(name=DEFAULT_TENANT)
            session.add(tenant)
            await session.flush()
        item_id = new_id()
        session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                source="manual",
                source_ref=f"demo-{new_id()}",
                raw={"title": "Demo item", "body": "Should I accept this meeting invite?"},
            )
        )
        await session.flush()
        await enqueue(session, tenant_id=tenant.id, kind=JobKind.PROCESS, item_id=item_id)
    return str(item_id)


def main() -> None:
    print(asyncio.run(create_demo_item()))  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
