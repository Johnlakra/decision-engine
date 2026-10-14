"""Feed catalog validation: the shipped catalogs and the rules that reject bad ones (FR-90)."""

from pathlib import Path

import pytest

from app.connectors.catalog import load_catalog_dir, parse_catalog
from app.connectors.feed_urls import feed_url

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
