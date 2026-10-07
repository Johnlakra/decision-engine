"""Structured logging tests (NFR-08)."""

import io
import json
import logging

import pytest

from app.core.logging import JsonFormatter, configure_logging, get_logger, log_context


@pytest.fixture
def stream() -> io.StringIO:
    buf = io.StringIO()
    configure_logging("INFO")
    root = logging.getLogger()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    return buf


def test_line_is_json_with_context_ids(stream: io.StringIO) -> None:
    """NFR-08: JSON lines carry bound ids."""
    with log_context(item_id="i1", job_id="j1", trace_id="t1", tenant_id="x"):
        get_logger("t").info("hello", extra={"count": 3})
    rec = json.loads(stream.getvalue().strip())
    assert rec["message"] == "hello" and rec["level"] == "INFO"
    assert rec["item_id"] == "i1" and rec["job_id"] == "j1"
    assert rec["trace_id"] == "t1" and rec["tenant_id"] == "x"
    assert rec["count"] == 3


def test_context_is_reset_after_exit(stream: io.StringIO) -> None:
    with log_context(item_id="i1"):
        pass
    get_logger("t").info("after")
    assert "item_id" not in json.loads(stream.getvalue().strip())


@pytest.mark.parametrize("field", ["body", "raw", "content", "payload"])
def test_sensitive_fields_redacted(stream: io.StringIO, field: str) -> None:
    """NFR-08: bodies never reach logs."""
    get_logger("t").info("x", extra={field: "secret text"})
    out = stream.getvalue()
    assert "secret text" not in out
    assert json.loads(out.strip())[field] == "[redacted]"


def test_exception_is_serialised(stream: io.StringIO) -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        get_logger("t").exception("failed")
    assert "ValueError" in json.loads(stream.getvalue().strip())["exc"]
