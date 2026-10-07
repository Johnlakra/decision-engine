"""Structured JSON logging with contextvar-bound ids (NFR-08)."""

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

CONTEXT_KEYS = ("item_id", "job_id", "trace_id", "tenant_id")
REDACTED_FIELDS = frozenset({"body", "raw", "content", "payload"})
REDACTED = "[redacted]"

_context: ContextVar[dict[str, str]] = ContextVar("log_context", default={})  # noqa: B039

_STANDARD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data.update(_context.get())
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                data[key] = value
        for key in REDACTED_FIELDS & data.keys():
            data[key] = REDACTED
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def log_context(**ids: object) -> Iterator[None]:
    """Bind item_id/job_id/trace_id/tenant_id to every log line in scope."""
    unknown = set(ids) - set(CONTEXT_KEYS)
    if unknown:
        raise TypeError(f"unknown log context keys: {sorted(unknown)}")
    merged = {**_context.get(), **{k: str(v) for k, v in ids.items()}}
    token: Token[dict[str, str]] = _context.set(merged)
    try:
        yield
    finally:
        _context.reset(token)
