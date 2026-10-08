"""Pure helpers of the ingest service (FR-07)."""

from datetime import UTC, datetime

from app.ingest.service import seconds_until_utc_midnight, start_of_utc_day


def test_start_of_utc_day() -> None:
    now = datetime(2026, 10, 8, 13, 5, 9, tzinfo=UTC)
    assert start_of_utc_day(now) == datetime(2026, 10, 8, tzinfo=UTC)


def test_seconds_until_midnight() -> None:
    assert seconds_until_utc_midnight(datetime(2026, 10, 8, 23, 59, 0, tzinfo=UTC)) == 60
    assert seconds_until_utc_midnight(datetime(2026, 10, 8, 0, 0, 0, tzinfo=UTC)) == 86400


def test_seconds_until_midnight_is_at_least_one() -> None:
    assert seconds_until_utc_midnight(datetime(2026, 10, 8, 23, 59, 59, 999999, tzinfo=UTC)) >= 1
