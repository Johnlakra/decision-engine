"""Optional Redis client: None when REDIS_URL is empty (Postgres fallback elsewhere)."""

import logging
from functools import lru_cache
from typing import Literal

from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> Redis | None:
    url = get_settings().redis_url
    if not url:
        return None
    return Redis.from_url(url, decode_responses=True)


async def ping_redis() -> Literal["ok", "down", "skipped"]:
    client = get_redis()
    if client is None:
        return "skipped"
    try:
        await client.ping()
    except Exception:
        logger.warning("redis ping failed", exc_info=True)
        return "down"
    return "ok"
