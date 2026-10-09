"""Per-item advisory lock shared by the worker and the resume API (C7, ADR 0003).

A session-level ``pg_try_advisory_lock`` held on a dedicated connection for the whole graph run, so
no API session ever holds an item row lock while LLM calls are in flight. Needs a direct (non
pooler) Postgres endpoint.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

from app.db.session import get_engine
from app.graph.errors import ItemBusy

__all__ = ["ItemBusy", "item_lock", "lock_key"]

LOCK_NAMESPACE = "decision-engine:item:"


def lock_key(item_id: uuid.UUID | str) -> int:
    """Stable signed 64-bit key for ``pg_try_advisory_lock``."""
    digest = hashlib.sha256(f"{LOCK_NAMESPACE}{item_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def item_lock(item_id: uuid.UUID | str) -> AsyncIterator[None]:
    """Hold the item lock or raise ``ItemBusy`` at once. Released on exit, even on cancellation."""
    key = {"k": lock_key(item_id)}
    async with get_engine().connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        got = (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), key)).scalar_one()
        if not got:
            raise ItemBusy(f"item {item_id} is being processed")
        try:
            yield
        finally:
            try:
                await asyncio.shield(conn.execute(text("SELECT pg_advisory_unlock(:k)"), key))
            except BaseException:
                await conn.invalidate()  # closing the session releases the lock server-side
                raise
