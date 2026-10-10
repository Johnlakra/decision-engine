"""Ingest request/response schemas; mirror /schemas/ingest_item.schema.json (C1, FR-01)."""

import json
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings

MAX_BULK = 500
MAX_CALLBACK_URL = 2000
MAX_PAYLOAD_BYTES = 512_000  # serialized JSON size of one item's payload (NFR-05)


def _check_url(value: str, *, schemes: tuple[str, ...]) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in schemes or not parsed.netloc:
        raise ValueError(f"must be an absolute {'/'.join(schemes)} URL")
    return value


class Hints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    niche: str | None = None
    language: str | None = None
    sensitivity: Literal["public", "private"] | None = None
    title: str | None = Field(default=None, max_length=500)
    body: str | None = Field(default=None, max_length=50000)
    url: str | None = None
    sender: str | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _check_url(value, schemes=("http", "https"))


class IngestItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    source_ref: str = Field(min_length=1, max_length=300)
    received_at: datetime | None = None
    payload: dict[str, Any] | list[Any] | str
    hints: Hints | None = None
    callback_url: str | None = Field(default=None, max_length=MAX_CALLBACK_URL)

    @field_validator("payload")
    @classmethod
    def _payload_size(cls, value: Any) -> Any:
        size = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes when serialized")
        return value

    @field_validator("callback_url")
    @classmethod
    def _callback(cls, value: str | None) -> str | None:
        """Syntax only (ADR 0004); the SSRF check runs at delivery time."""
        if value is None:
            return None
        allow_http = get_settings().webhook_allow_private_urls
        return _check_url(value, schemes=("http", "https") if allow_http else ("https",))


class IngestResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"id": "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e", "status": "new"}]
        }
    )

    id: str
    status: str


class BulkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[IngestItemIn] = Field(min_length=1, max_length=MAX_BULK)


class BulkRow(BaseModel):
    index: int
    id: str | None = None
    status: str | None = None
    error: str | None = None
