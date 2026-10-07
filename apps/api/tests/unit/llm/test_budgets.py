"""Budget counters and cool-downs (FR-60, NFR-06)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.llm.budgets import (
    BUDGET_TTL_SECONDS,
    COOLDOWN_SECONDS,
    InMemoryBudgetStore,
    MemoryCooldowns,
    RedisBudgetStore,
    ResilientBudgetStore,
    budget_key,
    seconds_until_utc_midnight,
)

NOON = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, int | str] = {}
        self.ttls: dict[str, int] = {}
        self.commands: list[str] = []

    async def get(self, key: str) -> str | None:
        self.commands.append("get")
        value = self.data.get(key)
        return None if value is None else str(value)

    async def incr(self, key: str) -> int:
        self.commands.append("incr")
        self.data[key] = int(self.data.get(key, 0)) + 1
        return int(self.data[key])

    async def expire(self, key: str, seconds: int) -> None:
        self.commands.append("expire")
        self.ttls[key] = seconds

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.commands.append("set")
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex

    async def exists(self, key: str) -> int:
        self.commands.append("exists")
        return int(key in self.data)


def redis_store(fake: FakeRedis, now: datetime = NOON) -> RedisBudgetStore:
    return RedisBudgetStore(fake, clock=lambda: now)  # type: ignore[arg-type]


def test_budget_key_format() -> None:
    assert budget_key("gemini", NOON) == "budget:gemini:20261007"


async def test_redis_incr_counts_and_sets_two_day_expiry_once() -> None:
    fake = FakeRedis()
    store = redis_store(fake)
    assert await store.incr("gemini") == 1
    assert await store.incr("gemini") == 2
    assert await store.count("gemini") == 2
    assert fake.ttls["budget:gemini:20261007"] == BUDGET_TTL_SECONDS == 172800
    assert fake.commands.count("expire") == 1  # keep Upstash command counts low


async def test_redis_counter_rolls_over_at_utc_midnight() -> None:
    fake = FakeRedis()
    await redis_store(fake, NOON).incr("groq")
    tomorrow = redis_store(fake, NOON + timedelta(days=1))
    assert await tomorrow.count("groq") == 0


async def test_redis_cooldown_uses_ttl() -> None:
    fake = FakeRedis()
    store = redis_store(fake)
    assert not await store.is_cooling("gemini")
    await store.cool_down("gemini", COOLDOWN_SECONDS)
    assert await store.is_cooling("gemini")
    assert fake.ttls["cooldown:gemini"] == 60


def test_seconds_until_utc_midnight() -> None:
    assert seconds_until_utc_midnight(NOON) == 12 * 3600
    late = datetime(2026, 10, 7, 23, 59, 30, tzinfo=UTC)
    assert seconds_until_utc_midnight(late) == 30
    ist = datetime(2026, 10, 8, 3, 0, tzinfo=timezone_ist())  # 21:30 UTC on the 7th
    assert seconds_until_utc_midnight(ist) == int(2.5 * 3600)


def timezone_ist() -> Any:
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Kolkata")


def test_memory_cooldown_expires() -> None:
    clock = [NOON]
    cooldowns = MemoryCooldowns(lambda: clock[0])
    cooldowns.set("groq", 60)
    assert cooldowns.is_cooling("groq")
    clock[0] = NOON + timedelta(seconds=59)
    assert cooldowns.is_cooling("groq")
    clock[0] = NOON + timedelta(seconds=60)
    assert not cooldowns.is_cooling("groq")


async def test_day_cooldown_lasts_until_midnight_in_memory() -> None:
    clock = [NOON]
    store = InMemoryBudgetStore(lambda: clock[0])
    await store.cool_down("gemini", seconds_until_utc_midnight(NOON))
    clock[0] = NOON + timedelta(hours=11, minutes=59)
    assert await store.is_cooling("gemini")
    clock[0] = NOON + timedelta(hours=12)
    assert not await store.is_cooling("gemini")


async def test_in_memory_counts_per_day() -> None:
    clock = [NOON]
    store = InMemoryBudgetStore(lambda: clock[0])
    await store.incr("a")
    await store.incr("a")
    assert await store.count("a") == 2
    clock[0] = NOON + timedelta(days=1)
    assert await store.count("a") == 0


class BrokenStore:
    async def count(self, provider: str) -> int:
        raise ConnectionError("redis down")

    incr = cool_down = is_cooling = count  # type: ignore[assignment]


async def test_resilient_store_falls_back_when_primary_fails() -> None:
    fallback = InMemoryBudgetStore()
    store = ResilientBudgetStore(BrokenStore(), fallback)  # type: ignore[arg-type]
    await store.cool_down("gemini", 60)
    assert await store.is_cooling("gemini")
    with pytest.raises(ConnectionError):
        await BrokenStore().count("x")
