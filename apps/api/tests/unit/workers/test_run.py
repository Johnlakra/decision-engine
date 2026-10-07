"""Pure worker helpers (NFR-02, NFR-03)."""

from datetime import datetime

from app.workers.run import asyncpg_dsn, is_active_hour, next_poll_delay


def test_next_poll_delay_grows_from_one_second_to_cap() -> None:
    delays = [next_poll_delay(n, 30) for n in range(0, 8)]
    assert delays == [1.0, 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


def test_next_poll_delay_never_below_one_second() -> None:
    assert next_poll_delay(5, 0) == 1.0


def test_is_active_hour_window_is_half_open() -> None:
    spec = (7, 23)
    assert is_active_hour(datetime(2026, 1, 1, 7, 0), spec)
    assert is_active_hour(datetime(2026, 1, 1, 22, 59), spec)
    assert not is_active_hour(datetime(2026, 1, 1, 23, 0), spec)
    assert not is_active_hour(datetime(2026, 1, 1, 6, 59), spec)


def test_full_day_is_always_active() -> None:
    assert is_active_hour(datetime(2026, 1, 1, 0, 0), (0, 24))
    assert is_active_hour(datetime(2026, 1, 1, 23, 59), (0, 24))


def test_asyncpg_dsn_drops_driver_suffix() -> None:
    assert asyncpg_dsn("postgresql+asyncpg://u:p@h:1/d") == "postgresql://u:p@h:1/d"
