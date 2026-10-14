"""Feed catalogs: ``data/feeds/<topic>.yaml`` validated and upserted as ``sources`` (Phase 2.3).

A catalog is a list of feeds for one topic. Each feed becomes one ``Source`` row keyed by
(tenant, slug), so re-running the loader updates rows instead of duplicating them.
"""

import uuid
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.feed_urls import (
    DEFAULT_HN_MIN_POINTS,
    MAX_HN_MIN_POINTS,
    TYPE_GOOGLE_NEWS,
    TYPE_RSS,
    feed_url,
)
from app.models.source import Source

SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,59}$"
NAME_PATTERN = r"^[a-z][a-z0-9_]{1,59}$"  # topics and niches use underscores
MAX_FEEDS_PER_TOPIC = 50


class FeedSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=SLUG_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    type: Literal["rss", "google_news", "hn"]
    url: str | None = None
    query: str | None = Field(default=None, max_length=200)
    min_points: int | None = Field(default=None, ge=0, le=MAX_HN_MIN_POINTS)

    @model_validator(mode="after")
    def _type_fields(self) -> "FeedSpec":
        if self.type == TYPE_RSS and not self.url:
            raise ValueError("rss feeds need a url")
        if self.type == TYPE_GOOGLE_NEWS and not self.query:
            raise ValueError("google_news feeds need a query")
        return self

    def config(self) -> dict[str, Any]:
        """The stored ``sources.config`` for this feed (only the fields its type uses)."""
        if self.type == TYPE_RSS:
            return {"url": self.url}
        if self.type == TYPE_GOOGLE_NEWS:
            return {"query": self.query}
        points = self.min_points if self.min_points is not None else DEFAULT_HN_MIN_POINTS
        return {"min_points": points}


class TopicCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(pattern=NAME_PATTERN)
    niche_hint: str | None = Field(default=None, pattern=NAME_PATTERN)
    feeds: list[FeedSpec] = Field(min_length=1, max_length=MAX_FEEDS_PER_TOPIC)

    @model_validator(mode="after")
    def _unique_slugs(self) -> "TopicCatalog":
        slugs = [feed.slug for feed in self.feeds]
        if len(slugs) != len(set(slugs)):
            raise ValueError("feed slugs must be unique within a topic")
        return self


def parse_catalog(document: object) -> TopicCatalog:
    """Validate an already-loaded YAML document. Raises ValueError naming the failing field."""
    return TopicCatalog.model_validate(document)


def load_catalog(path: Path) -> TopicCatalog:
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    try:
        return parse_catalog(document)
    except ValueError as error:
        raise ValueError(f"{path.name}: {error}") from error


def load_catalog_dir(directory: Path) -> list[TopicCatalog]:
    return [load_catalog(path) for path in sorted(directory.glob("*.yaml"))]


async def _existing_source(session: AsyncSession, tenant_id: uuid.UUID, slug: str) -> Source | None:
    stmt = select(Source).where(Source.tenant_id == tenant_id, Source.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_feed(
    session: AsyncSession, tenant_id: uuid.UUID, catalog: TopicCatalog, spec: FeedSpec
) -> bool:
    """Create or update one feed source. Returns True when a new row was created.

    A changed URL or query resets the HTTP cache cursor so the next poll is a full fetch.
    """
    config = spec.config()
    feed_url(spec.type, config)  # fail early on an unusable config (FeedConfigError)
    row = await _existing_source(session, tenant_id, spec.slug)
    if row is None:
        session.add(
            Source(
                tenant_id=tenant_id,
                type=spec.type,
                name=spec.name,
                slug=spec.slug,
                config=config,
                niche_hint=catalog.niche_hint,
                sensitivity="public",
                enabled=True,
            )
        )
        await session.flush()
        return True
    if row.config != config or row.type != spec.type:
        row.cursor = None
    row.type = spec.type
    row.name = spec.name
    row.config = config
    row.niche_hint = catalog.niche_hint
    row.enabled = True
    return False
