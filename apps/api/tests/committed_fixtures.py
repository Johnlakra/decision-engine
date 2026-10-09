"""Fixtures that commit real data (graph, worker and API acceptance tests).

Re-exported by tests/conftest.py so pytest discovers them.
"""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_rate_limiter
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine
from app.graph.setup import CHECKPOINT_SETUP_LOCK_KEY
from app.models import Tenant
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter

# ADR 0003: LangGraph owns these four tables; setup() creates them, the fixtures only empty them.
CHECKPOINT_TABLES = (
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
)


def psycopg_dsn(url: str) -> str:
    return url.replace("+asyncpg", "", 1)


async def _setup_checkpoint_tables(dsn: str) -> None:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row

    conn = await AsyncConnection.connect(
        dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row
    )
    try:
        await conn.execute("SELECT pg_advisory_lock(%s)", (CHECKPOINT_SETUP_LOCK_KEY,))
        try:
            await AsyncPostgresSaver(conn).setup()  # type: ignore[arg-type]
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK_KEY,))
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def checkpoint_db(migrated_db: str) -> str:
    """Migrated test database that also has the LangGraph checkpoint tables (once per session)."""
    asyncio.run(_setup_checkpoint_tables(psycopg_dsn(migrated_db)))
    return migrated_db


@pytest_asyncio.fixture
async def committed_db(
    checkpoint_db: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Real commits against the test DB; the app's own engine points at it for this test.

    Afterwards every app table and every checkpoint table is emptied.
    """
    monkeypatch.setenv("DATABASE_URL", checkpoint_db)
    get_settings.cache_clear()
    get_engine.cache_clear()
    engine = create_async_engine(checkpoint_db)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        names = [t.name for t in Base.metadata.sorted_tables] + list(CHECKPOINT_TABLES)
        quoted = ", ".join(f'"{n}"' for n in names)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
        await engine.dispose()
        await get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()


@pytest_asyncio.fixture
async def tenant_committed(committed_db: async_sessionmaker[AsyncSession]) -> Tenant:
    async with committed_db() as session:
        row = Tenant(name="Committed Tenant")
        session.add(row)
        await session.commit()
        return row


@pytest_asyncio.fixture
async def admin_key(
    committed_db: async_sessionmaker[AsyncSession], tenant_committed: Tenant
) -> str:
    """Full ``de_<prefix>_<secret>`` admin key for ``tenant_committed``."""
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with committed_db() as session:
        key = await create_api_key(session, tenant_committed.id, "test-admin", ["admin"], pepper)
        await session.commit()
        return key


@pytest_asyncio.fixture
async def api_client(
    committed_db: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    """httpx client on the ASGI app, using the committed DB and an in-memory rate limiter."""
    from app.graph import run as graph_run
    from app.main import create_app

    app = create_app()
    await graph_run.open_runtime()  # ASGITransport does not run the lifespan
    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        try:
            yield client
        finally:
            await graph_run.close_runtime()
