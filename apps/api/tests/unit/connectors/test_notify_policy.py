"""Quiet hours, daily cap and digest timing; bad settings fall back to defaults (FR-43)."""

from datetime import UTC, date, datetime

import pytest

from app.connectors.notify_policy import (
    DEFAULT_DIGEST_HOUR,
    DEFAULT_PING_CAP_PER_DAY,
    DEFAULT_QUIET_HOURS,
    NotifySettings,
    digest_due,
    digest_sent_on_from,
    in_quiet_hours,
    may_ping,
    settings_from,
)

DEFAULTS = NotifySettings(DEFAULT_QUIET_HOURS, DEFAULT_DIGEST_HOUR, DEFAULT_PING_CAP_PER_DAY)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(21, False), (22, True), (23, True), (0, True), (6, True), (7, False), (12, False)],
)
def test_quiet_hours_wrap_past_midnight(hour: int, expected: bool) -> None:
    assert in_quiet_hours(hour, (22, 7)) is expected


def test_same_start_and_end_means_no_quiet_hours() -> None:
    assert in_quiet_hours(3, (5, 5)) is False


def test_no_ping_during_quiet_hours_or_past_the_cap() -> None:
    assert may_ping(23, 0, DEFAULTS) is False
    assert may_ping(10, DEFAULT_PING_CAP_PER_DAY, DEFAULTS) is False
    assert may_ping(10, DEFAULT_PING_CAP_PER_DAY - 1, DEFAULTS) is True


def test_digest_is_due_once_per_local_day_after_the_digest_hour() -> None:
    before = datetime(2026, 10, 14, 7, 59, tzinfo=UTC)
    morning = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)

    assert digest_due(before, None, DEFAULTS) is False
    assert digest_due(morning, None, DEFAULTS) is True
    assert digest_due(morning, date(2026, 10, 14), DEFAULTS) is False
    assert digest_due(morning, date(2026, 10, 13), DEFAULTS) is True


def test_invalid_settings_are_replaced_by_defaults() -> None:
    settings = settings_from(
        {"quiet_hours": [25, "x"], "digest_hour": True, "ping_cap_per_day": -4}
    )

    assert settings == DEFAULTS


def test_valid_settings_are_honoured() -> None:
    settings = settings_from({"quiet_hours": [23, 6], "digest_hour": 9, "ping_cap_per_day": 5})

    assert settings == NotifySettings((23, 6), 9, 5)


def test_digest_sent_on_ignores_malformed_dates() -> None:
    assert digest_sent_on_from({"digest_sent_on": "2026-10-14"}) == date(2026, 10, 14)
    assert digest_sent_on_from({"digest_sent_on": "yesterday"}) is None
    assert digest_sent_on_from(None) is None
