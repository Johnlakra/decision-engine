"""``python -m app.graph.setup``: create the LangGraph checkpoint tables (ADR 0003)."""

import asyncio
import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.core.config import get_settings
from app.graph.checkpointer import psycopg_dsn

log = logging.getLogger(__name__)

CHECKPOINT_SETUP_LOCK_KEY = 7_340_001


async def setup_checkpoint_tables(dsn: str) -> None:
    """Idempotent: ``setup()`` under a session advisory lock so concurrent boots cannot race."""
    conn = await AsyncConnection.connect(
        psycopg_dsn(dsn), autocommit=True, prepare_threshold=0, row_factory=dict_row
    )
    try:
        await conn.execute("SELECT pg_advisory_lock(%s)", (CHECKPOINT_SETUP_LOCK_KEY,))
        try:
            await AsyncPostgresSaver(conn).setup()
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK_KEY,))
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(setup_checkpoint_tables(get_settings().database_url))
    log.info("checkpoint tables ready")


if __name__ == "__main__":
    main()
