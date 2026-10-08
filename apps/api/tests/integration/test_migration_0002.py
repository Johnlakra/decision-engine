"""Migration 0002: items.hints, callback_url and ix_items_tenant_created (FR-06, FR-07)."""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.db.base import Base
from app.db.migration_filters import include_object
from tests.committed_fixtures import CHECKPOINT_TABLES
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration

COLUMNS_SQL = (
    "SELECT column_name || ':' || data_type || ':' || is_nullable FROM information_schema.columns "
    "WHERE table_name='items' AND column_name IN ('hints','callback_url') ORDER BY 1"
)
INDEX_SQL = "SELECT indexdef FROM pg_indexes WHERE indexname='ix_items_tenant_created'"
CHECKPOINT_SQL = "SELECT tablename FROM pg_tables WHERE tablename LIKE 'checkpoint%'"


async def _rows(url: str, sql: str) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return [row[0] for row in await conn.execute(text(sql))]
    finally:
        await engine.dispose()


async def test_up_down_up(migrated_db: str) -> None:
    config = alembic_config()
    assert await _rows(migrated_db, COLUMNS_SQL) == ["callback_url:text:YES", "hints:jsonb:YES"]
    assert "(tenant_id, created_at)" in (await _rows(migrated_db, INDEX_SQL))[0]

    await asyncio.to_thread(command.downgrade, config, "0001")
    assert await _rows(migrated_db, COLUMNS_SQL) == []
    assert await _rows(migrated_db, INDEX_SQL) == []

    await asyncio.to_thread(command.upgrade, config, "head")
    assert len(await _rows(migrated_db, COLUMNS_SQL)) == 2
    assert len(await _rows(migrated_db, INDEX_SQL)) == 1


async def test_autogenerate_ignores_checkpoint_tables(checkpoint_db: str) -> None:
    """ADR 0003: checkpoint tables exist, yet autogenerate proposes nothing about them."""
    assert set(await _rows(checkpoint_db, CHECKPOINT_SQL)) == set(CHECKPOINT_TABLES)

    def _diff(conn: Connection) -> list[object]:
        ctx = MigrationContext.configure(conn, opts={"include_object": include_object})
        return list(compare_metadata(ctx, Base.metadata))

    engine = create_async_engine(checkpoint_db)
    try:
        async with engine.connect() as conn:
            diff = await conn.run_sync(_diff)
    finally:
        await engine.dispose()
    assert not [d for d in diff if "checkpoint" in repr(d)]
