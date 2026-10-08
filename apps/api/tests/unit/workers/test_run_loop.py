"""Worker loop without a database: active hours, LISTEN fallback, stop (NFR-02, NFR-03, NFR-08)."""

import asyncio
from datetime import datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.workers import run as run_mod
from app.workers.run import Worker, is_active_hour


class StubFactory:
    """Never used: run_once is replaced in these tests."""

    def __call__(self) -> Any:  # pragma: no cover
        raise AssertionError("no DB access expected")


def make_worker(**settings: Any) -> Worker:
    return Worker("w", Settings(_env_file=None, **settings), session_factory=StubFactory())  # type: ignore[arg-type]


# --- is_active_hour edges ---


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [(0, 0, False), (6, 59, False), (7, 0, True), (12, 30, True), (22, 59, True), (23, 0, False)],
)
def test_default_window_7_to_23_edges(hour: int, minute: int, expected: bool) -> None:
    assert is_active_hour(datetime(2026, 5, 5, hour, minute, 59), (7, 23)) is expected


def test_midnight_and_last_minute_with_24h_window() -> None:
    assert is_active_hour(datetime(2026, 5, 5, 0, 0, 0), (0, 24))
    assert is_active_hour(datetime(2026, 5, 5, 23, 59, 59), (0, 24))


def test_wrap_around_spec_is_rejected_by_settings_not_silently_inactive() -> None:
    """is_active_hour has no wrap-around support, so Settings must refuse such a spec."""
    with pytest.raises(ValueError, match="WORKER_ACTIVE_HOURS"):
        Settings(_env_file=None, worker_active_hours="22-6")  # type: ignore[arg-type]
    assert not is_active_hour(datetime(2026, 5, 5, 23, 0), (22, 6))  # documents the limitation


# --- LISTEN fallback ---


async def test_listen_connect_failure_returns_none_and_logs(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def refuse(dsn: str) -> None:
        raise OSError(f"cannot reach {dsn}")

    monkeypatch.setattr(run_mod.asyncpg, "connect", refuse)
    worker = make_worker(database_url="postgresql+asyncpg://u:hunter2@h/d")
    with caplog.at_level("WARNING", logger="app.workers"):
        assert await worker._listen() is None
    assert "polling only" in caplog.text
    assert "hunter2" not in caplog.text  # DSN password never logged


class FakeConn:
    def __init__(self, *, fail_listener: bool = False) -> None:
        self.fail_listener = fail_listener
        self.closed = False
        self.callbacks: list[Any] = []

    async def add_listener(self, channel: str, callback: Any) -> None:
        if self.fail_listener:
            raise RuntimeError("LISTEN not supported by pooler")
        self.callbacks.append(callback)

    async def close(self) -> None:
        self.closed = True


async def test_notify_callback_wakes_the_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = FakeConn()

    async def connect(dsn: str) -> FakeConn:
        return conn

    monkeypatch.setattr(run_mod.asyncpg, "connect", connect)
    worker = make_worker()
    assert await worker._listen() is conn
    assert not worker._wake.is_set()
    conn.callbacks[0](None, 1, "jobs_new", "process")
    assert worker._wake.is_set()


@pytest.mark.xfail(
    strict=True,
    reason="BUG app/workers/run.py:_listen (~line 119-122): if add_listener raises after "
    "asyncpg.connect succeeded (e.g. PgBouncer), the open connection is never closed.",
)
async def test_listen_failure_after_connect_closes_the_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = FakeConn(fail_listener=True)

    async def connect(dsn: str) -> FakeConn:
        return conn

    monkeypatch.setattr(run_mod.asyncpg, "connect", connect)
    assert await make_worker()._listen() is None
    assert conn.closed, "connection leaked after LISTEN failure"


# --- loop behaviour ---


async def _run_until(
    worker: Worker, monkeypatch: pytest.MonkeyPatch, **patches: Any
) -> list[float]:
    sleeps: list[float] = []

    async def no_listen() -> None:
        return None

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            worker.stop()

    monkeypatch.setattr(worker, "_listen", no_listen)
    monkeypatch.setattr(worker, "_sleep", fake_sleep)
    for name, value in patches.items():
        monkeypatch.setattr(worker, name, value)
    await asyncio.wait_for(worker.run_forever(), timeout=5)
    return sleeps


async def test_idle_polling_backs_off_1_2_4(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = make_worker(worker_idle_poll_seconds=30)

    async def empty() -> int:
        return 0

    async def no_reclaim() -> None:
        return None

    sleeps = await _run_until(worker, monkeypatch, run_once=empty, _maybe_reclaim=no_reclaim)
    assert sleeps == [1.0, 2.0, 4.0]


async def test_outside_active_hours_never_claims_and_sleeps_max_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = make_worker(worker_idle_poll_seconds=17, worker_active_hours="7-23")
    calls: list[str] = []

    async def claim() -> int:
        calls.append("claimed")
        return 0

    class Night(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "Night":  # type: ignore[override]
            return cls(2026, 5, 5, 3, 0, tzinfo=tz)

    monkeypatch.setattr(run_mod, "datetime", Night)
    sleeps = await _run_until(worker, monkeypatch, run_once=claim)
    assert calls == [] and sleeps == [17, 17, 17]


async def test_iteration_exception_is_logged_and_loop_survives(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    worker = make_worker()

    async def explode() -> int:
        raise RuntimeError("db hiccup")

    async def no_reclaim() -> None:
        return None

    with caplog.at_level("ERROR", logger="app.workers"):
        sleeps = await _run_until(worker, monkeypatch, run_once=explode, _maybe_reclaim=no_reclaim)
    assert len(sleeps) == 3
    assert "worker iteration failed" in caplog.text


async def test_busy_worker_does_not_sleep_between_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = make_worker()
    batches = iter([5, 5, 0, 0, 0])

    async def next_batch() -> int:
        return next(batches)

    async def no_reclaim() -> None:
        return None

    sleeps = await _run_until(worker, monkeypatch, run_once=next_batch, _maybe_reclaim=no_reclaim)
    assert sleeps == [1.0, 2.0, 4.0]


async def test_listener_is_closed_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    worker = make_worker()
    conn = FakeConn()

    async def listen() -> FakeConn:
        return conn

    async def empty() -> int:
        worker.stop()
        return 0

    async def no_reclaim() -> None:
        return None

    monkeypatch.setattr(worker, "_listen", listen)
    monkeypatch.setattr(worker, "run_once", empty)
    monkeypatch.setattr(worker, "_maybe_reclaim", no_reclaim)
    await asyncio.wait_for(worker.run_forever(), timeout=5)
    assert conn.closed


async def test_sleep_returns_early_when_woken_and_clears_the_flag() -> None:
    worker = make_worker()
    worker._wake.set()
    await asyncio.wait_for(worker._sleep(30), timeout=1)
    assert not worker._wake.is_set()


async def test_sleep_times_out_quietly() -> None:
    await asyncio.wait_for(make_worker()._sleep(0.01), timeout=1)
