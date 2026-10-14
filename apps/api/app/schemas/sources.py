"""Source API shapes (FR-90, ADR 0010). Never exposes config, secret_enc or oauth_enc."""

import ipaddress
import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.connectors.feed_urls import (
    MAX_QUERY_CHARS,
    TYPE_GOOGLE_NEWS,
    TYPE_RSS,
    FeedConfigError,
    feed_url,
)

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,59}$"
NICHE_PATTERN = r"^[a-z][a-z0-9_]{1,59}$"
MAX_URL_CHARS = 2048
CREATABLE_TYPES = (TYPE_RSS, TYPE_GOOGLE_NEWS)

EXAMPLE_OUT: dict[str, Any] = {
    "id": "0192f0c2-7a1e-7c3b-9d1e-2f4a5b6c7d8e",
    "type": "rss",
    "name": "Example feed",
    "slug": "example-feed",
    "enabled": True,
    "niche_hint": "news_radar",
    "last_polled_at": "2026-10-14T05:00:00Z",
    "error_count": 0,
    "items_today": 4,
}


class SourceOut(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [EXAMPLE_OUT]})

    id: uuid.UUID
    type: str
    name: str
    slug: str
    enabled: bool
    niche_hint: str | None
    last_polled_at: datetime | None
    error_count: int
    items_today: int


class SourceList(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"data": [EXAMPLE_OUT]}]})

    data: list[SourceOut]


class SourcePatch(BaseModel):
    """Only ``enabled`` can change (ADR 0010); any other key is a 422."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"enabled": False}]})

    enabled: StrictBool


class SourceIn(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "type": "rss",
                    "name": "Example feed",
                    "slug": "example-feed",
                    "config": {"url": "https://example.com/feed.xml"},
                    "niche_hint": "news_radar",
                },
                {
                    "type": "google_news",
                    "name": "Punjab rice news",
                    "slug": "punjab-rice",
                    "config": {"query": "punjab rice msp"},
                },
            ]
        },
    )

    type: str = Field(description="Phase 3 accepts rss and google_news only")
    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str, Field(pattern=SLUG_PATTERN)]
    config: dict[str, Any] = Field(description="rss: {url}; google_news: {query}")
    niche_hint: Annotated[str, Field(pattern=NICHE_PATTERN)] | None = None

    @model_validator(mode="after")
    def _type_and_config(self) -> "SourceIn":
        if self.type not in CREATABLE_TYPES:
            raise ValueError(f"source type {self.type!r} is not available yet (rss, google_news)")
        key = "url" if self.type == TYPE_RSS else "query"
        if set(self.config) != {key}:
            raise ValueError(f"config for {self.type} must contain exactly {key!r}")
        value = self.config[key]
        if not isinstance(value, str):
            raise ValueError(f"config.{key} must be a string")
        if self.type == TYPE_RSS:
            _check_https_url(value)
        elif len(value) > MAX_QUERY_CHARS:
            raise ValueError(f"config.query is longer than {MAX_QUERY_CHARS} characters")
        try:
            feed_url(self.type, {key: value})
        except FeedConfigError as exc:
            raise ValueError(str(exc)) from exc
        return self


def _check_https_url(value: str) -> None:
    """https, a host, no credentials, and no private IP literal. The poll re-checks DNS."""
    if len(value) > MAX_URL_CHARS:
        raise ValueError("config.url is too long")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        parts.port  # noqa: B018 - validates the port
    except ValueError as exc:
        raise ValueError("config.url is not a valid URL") from exc
    if parts.scheme != "https" or not host:
        raise ValueError("config.url must be an https URL with a host")
    if parts.username or parts.password:
        raise ValueError("config.url must not contain credentials")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError("config.url must not point at a private address")
