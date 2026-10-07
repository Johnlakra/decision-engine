"""Daily budgets and cool-downs (FR-60, NFR-06).

Redis when REDIS_URL is set (INCR + EXPIRE 2 d), otherwise count today's llm_usage rows in Postgres.
Cool-downs live in Redis when available, otherwise in process memory.
"""

import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.llm_usage import LlmUsage

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 60
BUDGET_TTL_SECONDS = 2 * 24 * 3600

Clock = Callable[[], datetime]
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def day_stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%d")


def budget_key(provider: str, now: datetime) -> str:
    return f"budget:{provider}:{day_stamp(now)}"


def cooldown_key(provider: str) -> str:
    return f"cooldown:{provider}"


def seconds_until_utc_midnight(now: datetime) -> int:
    utc = now.astimezone(UTC)
    midnight = (utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - utc).total_seconds()))


class BudgetStore(Protocol):
    async def count(self, provider: str) -> int:
        """Attempts made today (UTC)."""
        ...

    async def incr(self, provider: str) -> int:
        """Record one attempt and return today's count."""
        ...

    async def cool_down(self, provider: str, seconds: int) -> None: ...

    async def is_cooling(self, provider: str) -> bool: ...


class MemoryCooldowns:
    """Per-process cool-downs used when Redis is absent."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self._clock = clock
        self._until: dict[str, datetime] = {}

    def set(self, provider: str, seconds: int) -> None:
        self._until[provider] = self._clock() + timedelta(seconds=seconds)

    def is_cooling(self, provider: str) -> bool:
        until = self._until.get(provider)
        if until is None:
            return False
        if self._clock() >= until:
            del self._until[provider]
            return False
        return True


class RedisBudgetStore:
    def __init__(self, redis: Redis, clock: Clock = utcnow) -> None:
        self._redis = redis
        self._clock = clock

    async def count(self, provider: str) -> int:
        raw = await self._redis.get(budget_key(provider, self._clock()))
        return int(raw) if raw else 0

    async def incr(self, provider: str) -> int:
        key = budget_key(provider, self._clock())
        value = int(await self._redis.incr(key))
        if value == 1:
            await self._redis.expire(key, BUDGET_TTL_SECONDS)
        return value

    async def cool_down(self, provider: str, seconds: int) -> None:
        await self._redis.set(cooldown_key(provider), "1", ex=max(1, seconds))

    async def is_cooling(self, provider: str) -> bool:
        return bool(await self._redis.exists(cooldown_key(provider)))


class PostgresBudgetStore:
    """Counts today's llm_usage rows (every attempt writes one), so incr is a read."""

    def __init__(self, session_factory: SessionFactory, clock: Clock = utcnow) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._cooldowns = MemoryCooldowns(clock)

    async def count(self, provider: str) -> int:
        now = self._clock().astimezone(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = (
            select(func.count())
            .select_from(LlmUsage)
            .where(LlmUsage.provider == provider, LlmUsage.created_at >= start)
        )
        async with self._session_factory() as session:
            return int((await session.execute(stmt)).scalar_one())

    async def incr(self, provider: str) -> int:
        return await self.count(provider)

    async def cool_down(self, provider: str, seconds: int) -> None:
        self._cooldowns.set(provider, seconds)

    async def is_cooling(self, provider: str) -> bool:
        return self._cooldowns.is_cooling(provider)


class ResilientBudgetStore:
    """Primary (Redis) with a fallback (Postgres + memory) when the primary raises."""

    def __init__(self, primary: BudgetStore, fallback: BudgetStore) -> None:
        self._primary = primary
        self._fallback = fallback

    async def _try[T](self, op: Callable[[BudgetStore], Awaitable[T]]) -> T:
        try:
            return await op(self._primary)
        except Exception:
            logger.warning("budget store primary failed, using fallback", exc_info=True)
            return await op(self._fallback)

    async def count(self, provider: str) -> int:
        return await self._try(lambda s: s.count(provider))

    async def incr(self, provider: str) -> int:
        return await self._try(lambda s: s.incr(provider))

    async def cool_down(self, provider: str, seconds: int) -> None:
        await self._try(lambda s: s.cool_down(provider, seconds))

    async def is_cooling(self, provider: str) -> bool:
        return await self._try(lambda s: s.is_cooling(provider))


_store: BudgetStore | None = None


def get_budget_store() -> BudgetStore:
    """Process singleton: Redis (falling back to Postgres) when configured, else Postgres."""
    global _store
    if _store is None:
        from app.db.redis import get_redis
        from app.db.session import session_scope

        postgres = PostgresBudgetStore(session_scope)
        redis = get_redis()
        _store = ResilientBudgetStore(RedisBudgetStore(redis), postgres) if redis else postgres
    return _store


def set_budget_store(store: BudgetStore | None) -> None:
    """Install (tests) or reset the singleton."""
    global _store
    _store = store


class InMemoryBudgetStore:
    """Process-local store: smoke runs and tests (no Redis, no database)."""

    def __init__(self, clock: Clock = utcnow) -> None:
        self._clock = clock
        self._counts: dict[str, int] = {}
        self._cooldowns = MemoryCooldowns(clock)

    async def count(self, provider: str) -> int:
        return self._counts.get(budget_key(provider, self._clock()), 0)

    async def incr(self, provider: str) -> int:
        key = budget_key(provider, self._clock())
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def cool_down(self, provider: str, seconds: int) -> None:
        self._cooldowns.set(provider, seconds)

    async def is_cooling(self, provider: str) -> bool:
        return self._cooldowns.is_cooling(provider)
