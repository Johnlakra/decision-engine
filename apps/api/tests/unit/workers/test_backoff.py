"""Backoff schedule and error sanitising (NFR-02)."""

from datetime import timedelta

from app.workers.queue import MAX_ERROR_CHARS, backoff_delay, describe_exception, safe_error


def test_backoff_schedule_doubles_from_30s() -> None:
    seconds = [backoff_delay(n).total_seconds() for n in range(1, 6)]
    assert seconds == [30, 60, 120, 240, 480]


def test_backoff_is_capped_at_30_minutes() -> None:
    assert backoff_delay(20) == timedelta(minutes=30)


def test_backoff_zero_attempts_uses_base() -> None:
    assert backoff_delay(0) == timedelta(seconds=30)


def test_safe_error_keeps_first_line_and_caps_length() -> None:
    assert safe_error("boom\nsecret body line") == "boom"
    assert len(safe_error("x" * 1000)) == MAX_ERROR_CHARS


def test_describe_exception_omits_message() -> None:
    assert describe_exception(ValueError("private email body")) == "ValueError"
