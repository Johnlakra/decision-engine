"""Feed catalog validation: the shipped catalogs and the rules that reject bad ones (FR-90)."""

import uuid
from pathlib import Path

import pytest

from app.connectors import catalog as catalog_mod
from app.connectors.catalog import (
    FeedSpec,
    TopicCatalog,
    load_catalog_dir,
    parse_catalog,
    upsert_feed,
)
from app.connectors.feed_urls import feed_url
from app.models.source import Source

SHIPPED_FEEDS_DIR = Path(__file__).resolve().parents[5] / "data" / "feeds"


def test_every_shipped_catalog_validates_and_polls_a_usable_url() -> None:
    catalogs = load_catalog_dir(SHIPPED_FEEDS_DIR)

    assert {catalog.topic for catalog in catalogs} == {
        "ai",
        "crypto",
        "india_tech",
        "punjab_agri_policy",
    }
    for catalog in catalogs:
        assert len(catalog.feeds) >= 2
        for spec in catalog.feeds:
            assert feed_url(spec.type, spec.config()).startswith("https://")


def test_feed_types_need_their_own_field() -> None:
    with pytest.raises(ValueError, match="rss feeds need a url"):
        parse_catalog({"topic": "ai", "feeds": [{"slug": "a-one", "name": "A", "type": "rss"}]})
    with pytest.raises(ValueError, match="google_news feeds need a query"):
        parse_catalog(
            {"topic": "ai", "feeds": [{"slug": "a-one", "name": "A", "type": "google_news"}]}
        )


def test_duplicate_slugs_inside_a_topic_are_rejected() -> None:
    feed = {"slug": "dup-feed", "name": "A", "type": "hn"}
    with pytest.raises(ValueError, match="unique"):
        parse_catalog({"topic": "ai", "feeds": [feed, dict(feed, name="B")]})


def test_unknown_keys_are_rejected_so_typos_do_not_pass_silently() -> None:
    document = {
        "topic": "ai",
        "feeds": [{"slug": "a-one", "name": "A", "type": "hn", "minpoints": 5}],
    }
    with pytest.raises(ValueError):
        parse_catalog(document)


def test_hn_config_defaults_its_points_floor() -> None:
    catalog = parse_catalog(
        {"topic": "ai", "feeds": [{"slug": "a-one", "name": "A", "type": "hn"}]}
    )

    assert catalog.feeds[0].config() == {"min_points": 50}


# ---- upsert_feed keeps the user's enabled switch (ADR 0010) -----------------------------------


class _RecordingSession:
    def __init__(self) -> None:
        self.added: list[Source] = []

    def add(self, row: Source) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _catalog_and_spec() -> tuple[TopicCatalog, FeedSpec]:
    catalog = parse_catalog(
        {
            "topic": "ai",
            "niche_hint": "news_radar",
            "feeds": [{"slug": "a-one", "name": "A", "type": "rss", "url": "https://a.io/feed"}],
        }
    )
    return catalog, catalog.feeds[0]


async def test_upsert_feed_inserts_new_rows_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def missing(*_: object) -> None:
        return None

    monkeypatch.setattr(catalog_mod, "_existing_source", missing)
    session = _RecordingSession()
    catalog, spec = _catalog_and_spec()

    created = await upsert_feed(session, uuid.uuid4(), catalog, spec)  # type: ignore[arg-type]

    assert created is True
    assert session.added[0].enabled is True


async def test_upsert_feed_keeps_a_disabled_row_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = Source(
        type="rss",
        name="Old name",
        slug="a-one",
        config={"url": "https://a.io/feed"},
        enabled=False,
        error_count=4,
        cursor={"etag": "x"},
    )

    async def found(*_: object) -> Source:
        return existing

    monkeypatch.setattr(catalog_mod, "_existing_source", found)
    catalog, spec = _catalog_and_spec()

    created = await upsert_feed(_RecordingSession(), uuid.uuid4(), catalog, spec)  # type: ignore[arg-type]

    assert created is False
    assert existing.enabled is False  # the user's switch wins over the loader
    assert existing.name == "A" and existing.niche_hint == "news_radar"  # other fields refresh
    assert existing.error_count == 4 and existing.cursor == {"etag": "x"}
