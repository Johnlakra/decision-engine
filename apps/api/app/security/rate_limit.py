"""Per-key rate limiting: Redis fixed window, in-process fallback (FR-07, ADR 0002)."""

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    retry_after_s: int = 0


class RateLimiter(Protocol):
    async def hit(self, key: str, limit: int, window_s: int = 60) -> RateDecision: ...


class _Counter(Protocol):
    def incr(self, name: str) -> Awaitable[int]: ...
    def expire(self, name: str, time: int) -> Awaitable[object]: ...


def _window(now: float, window_s: int) -> tuple[int, int]:
    """Return (window_start, seconds until the window ends, at least 1)."""
    start = int(now // window_s) * window_s
    return start, max(1, math.ceil(start + window_s - now))


class MemoryRateLimiter:
    """Fixed window in one process. With N processes the effective limit is N x limit."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = asyncio.Lock()
        self._windows: dict[tuple[str, int], tuple[int, float]] = {}

    async def hit(self, key: str, limit: int, window_s: int = 60) -> RateDecision:
        async with self._lock:
            now = self._clock()
            self._windows = {k: v for k, v in self._windows.items() if v[1] > now}
            start, retry = _window(now, window_s)
            count = self._windows.get((key, start), (0, 0.0))[0] + 1
            self._windows[(key, start)] = (count, start + window_s)
            return RateDecision(count <= limit, 0 if count <= limit else retry)


class RedisRateLimiter:
    """Fixed window: INCR then EXPIRE (2 commands per request)."""

    def __init__(self, client: _Counter, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._clock = clock

    async def hit(self, key: str, limit: int, window_s: int = 60) -> RateDecision:
        start, retry = _window(self._clock(), window_s)
        name = f"rl:{key}:{start}"
        count = await self._client.incr(name)
        await self._client.expire(name, window_s)
        return RateDecision(count <= limit, 0 if count <= limit else retry)


class ResilientRateLimiter:
    """Use the primary limiter; on any error use the fallback for that request."""

    def __init__(self, primary: RateLimiter, fallback: RateLimiter) -> None:
        self._primary = primary
        self._fallback = fallback

    async def hit(self, key: str, limit: int, window_s: int = 60) -> RateDecision:
        try:
            return await self._primary.hit(key, limit, window_s)
        except Exception:
            logger.warning("rate limiter backend failed; using in-memory fallback", exc_info=True)
            return await self._fallback.hit(key, limit, window_s)
