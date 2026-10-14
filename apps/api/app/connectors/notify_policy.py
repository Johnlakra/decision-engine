"""Notification policy: quiet hours, daily ping cap, digest timing (FR-43). Pure, tenant-local time.

Settings come from ``tenant_settings.settings``; anything missing or invalid falls back to the
defaults below, so a bad settings row can never make the bot ping at 3 a.m.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

DEFAULT_QUIET_HOURS = (22, 7)  # local hours [start, end); wraps past midnight
DEFAULT_DIGEST_HOUR = 8
DEFAULT_PING_CAP_PER_DAY = 3
MAX_PING_CAP_PER_DAY = 50
MIN_URGENCY_FOR_PING = 2  # docs/REQUIREMENTS.md FR-43: instant ping for urgency 2
DIGEST_SENT_ON_KEY = "digest_sent_on"


@dataclass(frozen=True)
class NotifySettings:
    quiet_hours: tuple[int, int]
    digest_hour: int
    ping_cap_per_day: int


def _hour(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 23:
        return value
    return None


def _quiet_hours(value: object) -> tuple[int, int]:
    if isinstance(value, list) and len(value) == 2:
        start, end = _hour(value[0]), _hour(value[1])
        if start is not None and end is not None:
            return (start, end)
    return DEFAULT_QUIET_HOURS


def _cap(value: object) -> int:
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value <= MAX_PING_CAP_PER_DAY
    ):
        return value
    return DEFAULT_PING_CAP_PER_DAY


def settings_from(raw: Mapping[str, Any] | None) -> NotifySettings:
    """Validated settings. Invalid entries are replaced by defaults, never trusted."""
    source = raw or {}
    digest_hour = _hour(source.get("digest_hour"))
    return NotifySettings(
        quiet_hours=_quiet_hours(source.get("quiet_hours")),
        digest_hour=digest_hour if digest_hour is not None else DEFAULT_DIGEST_HOUR,
        ping_cap_per_day=_cap(source.get("ping_cap_per_day")),
    )


def in_quiet_hours(hour: int, quiet: tuple[int, int]) -> bool:
    start, end = quiet
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def may_ping(local_hour: int, pings_today: int, settings: NotifySettings) -> bool:
    return not in_quiet_hours(local_hour, settings.quiet_hours) and (
        pings_today < settings.ping_cap_per_day
    )


def digest_due(local_now: datetime, digest_sent_on: date | None, settings: NotifySettings) -> bool:
    """One digest per local day, at or after the digest hour."""
    return local_now.hour >= settings.digest_hour and digest_sent_on != local_now.date()


def digest_sent_on_from(raw: Mapping[str, Any] | None) -> date | None:
    value = (raw or {}).get(DIGEST_SENT_ON_KEY)
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
