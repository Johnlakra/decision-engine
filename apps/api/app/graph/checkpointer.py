"""AsyncPostgresSaver over a small psycopg 3 pool (ADR 0003 section 2)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

POOL_MIN_SIZE = 1
POOL_MAX_SIZE = 2


def psycopg_dsn(database_url: str) -> str:
    """The SQLAlchemy URL without the asyncpg driver suffix."""
    return database_url.replace("+asyncpg", "", 1)


@asynccontextmanager
async def open_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    """Open the pool and yield a saver. Use a direct (non-pooler) endpoint only."""
    pool = AsyncConnectionPool(
        psycopg_dsn(dsn),
        min_size=POOL_MIN_SIZE,
        max_size=POOL_MAX_SIZE,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    try:
        yield AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    finally:
        await pool.close()
