"""Base fixtures: settings override, integration marker and skip logic."""

import os
import socket
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command
from app.core.config import get_settings
from app.models import Tenant
from tests.committed_fixtures import (  # noqa: F401  (fixtures re-exported for discovery)
    admin_key,
    api_client,
    checkpoint_db,
    committed_db,
    tenant_committed,
)

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://de:de@localhost:5432/de_test"


def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _db_reachable(url: str) -> bool:
    parsed = urlparse(url)
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 1):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _db_reachable(test_database_url()):
        return
    skip = pytest.mark.skip(
        reason=(
            f"SKIPPING integration tests: Postgres at {test_database_url()} is unreachable. "
            "Start the db (docker compose up -d db) or set TEST_DATABASE_URL."
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Override environment variables for one test; the settings cache is reset around it."""
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


API_ROOT = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", test_database_url())
    return config


@pytest.fixture(scope="session")
def migrated_db() -> str:
    """Bring the test database to head once per session."""
    command.upgrade(alembic_config(), "head")
    return test_database_url()


@pytest_asyncio.fixture
async def db_session(migrated_db: str) -> AsyncIterator[AsyncSession]:
    """Real Postgres session inside an outer transaction that is rolled back per test."""
    engine = create_async_engine(migrated_db)
    async with engine.connect() as connection:
        outer = await connection.begin()
        session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def tenant(db_session: AsyncSession) -> Tenant:
    row = Tenant(name="Test Tenant")
    db_session.add(row)
    await db_session.flush()
    return row
