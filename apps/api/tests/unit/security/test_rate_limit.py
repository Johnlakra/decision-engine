"""Rate limiters (FR-07, ADR 0002)."""

import pytest

from app.security.rate_limit import (
    MemoryRateLimiter,
    RedisRateLimiter,
    ResilientRateLimiter,
)


class Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def test_memory_allows_up_to_limit_then_denies_with_retry_after() -> None:
    clock = Clock(1000.0)  # window 960..1020, 20 s left
    limiter = MemoryRateLimiter(clock)
    results = [await limiter.hit("k", 3) for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[3].retry_after_s == 20


async def test_memory_window_rolls_over_and_keys_are_independent() -> None:
    clock = Clock(1000.0)
    limiter = MemoryRateLimiter(clock)
    await limiter.hit("a", 1)
    assert not (await limiter.hit("a", 1)).allowed
    assert (await limiter.hit("b", 1)).allowed
    clock.now = 1021.0
    assert (await limiter.hit("a", 1)).allowed


async def test_memory_drops_expired_windows() -> None:
    clock = Clock(1000.0)
    limiter = MemoryRateLimiter(clock)
    for i in range(50):
        await limiter.hit(f"k{i}", 5)
    clock.now = 5000.0
    await limiter.hit("x", 5)
    assert len(limiter._windows) == 1


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.commands: list[str] = []

    async def incr(self, name: str) -> int:
        self.commands.append("incr")
        self.counts[name] = self.counts.get(name, 0) + 1
        return self.counts[name]

    async def expire(self, name: str, time: int) -> bool:
        self.commands.append("expire")
        return True


class BrokenRedis:
    async def incr(self, name: str) -> int:
        raise ConnectionError("redis down")

    async def expire(self, name: str, time: int) -> bool:
        raise ConnectionError("redis down")


async def test_redis_limiter_uses_two_commands_and_denies_over_limit() -> None:
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis, Clock(1000.0))
    first = await limiter.hit("k", 1)
    second = await limiter.hit("k", 1)
    assert first.allowed and not second.allowed and second.retry_after_s == 20
    assert redis.commands == ["incr", "expire", "incr", "expire"]


async def test_redis_error_falls_back_to_memory(caplog: pytest.LogCaptureFixture) -> None:
    limiter = ResilientRateLimiter(RedisRateLimiter(BrokenRedis()), MemoryRateLimiter())
    assert (await limiter.hit("k", 1)).allowed
    assert not (await limiter.hit("k", 1)).allowed
    assert "fallback" in caplog.text
