"""Load the starter feed catalogs from ``data/feeds/*.yaml`` as sources (Phase 2.3).

Usage: ``python -m scripts.load_feeds``. Idempotent: feeds are keyed by slug per tenant, so a
re-run updates rows instead of creating duplicates. Polling happens later, via
``python -m app.connectors.schedule`` and the worker.
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.catalog import TopicCatalog, load_catalog_dir, upsert_feed
from app.core.config import get_settings
from app.db.session import session_scope
from app.db.tenants import ensure_default_tenant

FEEDS_RELATIVE_PATH = Path("feeds")


@dataclass(frozen=True)
class LoadResult:
    created: int
    updated: int


def feeds_dir() -> Path:
    return get_settings().data_dir / FEEDS_RELATIVE_PATH


async def load_catalogs(session: AsyncSession, catalogs: list[TopicCatalog]) -> LoadResult:
    tenant_id = await ensure_default_tenant(session)
    created = 0
    total = 0
    for catalog in catalogs:
        for spec in catalog.feeds:
            total += 1
            created += int(await upsert_feed(session, tenant_id, catalog, spec))
    return LoadResult(created=created, updated=total - created)


async def run(directory: Path) -> LoadResult:
    catalogs = load_catalog_dir(directory)
    async with session_scope() as session:
        return await load_catalogs(session, catalogs)


def main() -> int:
    try:
        result = asyncio.run(run(feeds_dir()))
    except ValueError as error:
        print(f"load_feeds: {error}", file=sys.stderr)  # noqa: T201 - CLI output
        return 2
    print(f"feeds: {result.created} created, {result.updated} updated")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
