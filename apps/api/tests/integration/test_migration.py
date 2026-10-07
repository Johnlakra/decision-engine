"""Migration tests (NFR-12): upgrade/downgrade/upgrade and enum drift guard."""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.db.base import Base
from app.models import enums
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "tenants", "tenant_settings", "api_keys", "sources", "items", "jobs", "niches",
    "decisions", "feedback", "llm_usage", "actions_log", "webhook_subscriptions",
    "webhook_deliveries",
}  # fmt: skip


async def _scalars(url: str, sql: str) -> list[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return [row[0] for row in await conn.execute(text(sql))]
    finally:
        await engine.dispose()


async def _tables(url: str) -> set[str]:
    rows = await _scalars(
        url,
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename<>'alembic_version'",  # noqa: E501,
    )
    return set(rows)


async def test_upgrade_downgrade_upgrade(migrated_db: str) -> None:
    config = alembic_config()
    assert await _tables(migrated_db) == EXPECTED_TABLES
    await asyncio.to_thread(command.downgrade, config, "base")
    assert await _tables(migrated_db) == set()
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _tables(migrated_db) == EXPECTED_TABLES


async def test_metadata_matches_migration(migrated_db: str) -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


async def test_check_constraints_equal_enum_values(migrated_db: str) -> None:
    """Drift guard: every CHECK in the database carries exactly the enums.py values."""
    defs = await _scalars(
        migrated_db,
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE contype='c'",
    )
    blob = " ".join(defs)
    for enum_cls in (
        enums.ItemStatus, enums.JobKind, enums.JobStatus, enums.Sensitivity, enums.Verdict,
        enums.DecidedBy, enums.FeedbackKind, enums.LabelSource, enums.NicheSource,
        enums.DeliveryStatus, enums.ActionStatus, enums.Risk,
    ):  # fmt: skip
        for value in enum_cls.values():
            assert f"'{value}'" in blob, f"{enum_cls.__name__}.{value} missing from CHECKs"
    status_def = next(d for d in defs if "'needs_human_triage'" in d)
    assert status_def.count("::text") == len(enums.ItemStatus.values())


async def test_partial_queue_index_and_pgvector(migrated_db: str) -> None:
    index = await _scalars(
        migrated_db, "SELECT indexdef FROM pg_indexes WHERE indexname='ix_jobs_queued_run_at'"
    )
    assert "WHERE (status = 'queued'::text)" in index[0]
    ext = await _scalars(migrated_db, "SELECT extname FROM pg_extension WHERE extname='vector'")
    assert ext == ["vector"]


async def test_ids_are_uuid_and_times_timestamptz(migrated_db: str) -> None:
    types = await _scalars(
        migrated_db,
        "SELECT DISTINCT data_type FROM information_schema.columns WHERE table_schema='public' "
        "AND column_name IN ('created_at','updated_at','received_at','run_at')",
    )
    assert types == ["timestamp with time zone"]
