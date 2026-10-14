"""Feed URL builders, feed type dispatch and the Hacker News parser (FR-90)."""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from app.connectors.feed_parse import FeedParseError
from app.connectors.feed_urls import (
    DEFAULT_HN_MIN_POINTS,
    FeedConfigError,
    feed_url,
    google_news_url,
    hn_search_url,
)
from app.connectors.hn import HN_ITEM_URL, parse_hn


def test_google_news_url_targets_india_english_and_encodes_query() -> None:
    url = google_news_url("AI startups & funding")

    parts = urlsplit(url)
    query = parse_qs(parts.query)
    assert parts.netloc == "news.google.com"
    assert query["q"] == ["AI startups & funding"]
    assert query["hl"] == ["en-IN"]
    assert query["gl"] == ["IN"]
    assert query["ceid"] == ["IN:en"]


def test_blank_google_news_query_is_rejected() -> None:
    with pytest.raises(FeedConfigError):
        google_news_url("   ")


def test_hn_url_uses_points_floor() -> None:
    query = parse_qs(urlsplit(hn_search_url()).query)

    assert query["numericFilters"] == [f"points>{DEFAULT_HN_MIN_POINTS}"]
    assert query["tags"] == ["story"]


@pytest.mark.parametrize("bad", [-1, 10_001])
def test_hn_points_out_of_range_are_rejected(bad: int) -> None:
    with pytest.raises(FeedConfigError):
        hn_search_url(bad)


def test_feed_url_dispatch_by_type() -> None:
    assert feed_url("rss", {"url": "https://example.com/feed.xml"}) == (
        "https://example.com/feed.xml"
    )
    assert feed_url("google_news", {"query": "crypto india"}).startswith(
        "https://news.google.com/rss/search?"
    )
    assert feed_url("hn", {}) == hn_search_url(DEFAULT_HN_MIN_POINTS)


def test_feed_url_rejects_unknown_type_and_bad_config() -> None:
    with pytest.raises(FeedConfigError):
        feed_url("carrier_pigeon", {})
    with pytest.raises(FeedConfigError):
        feed_url("rss", {"url": ""})
    with pytest.raises(FeedConfigError):
        feed_url("hn", {"min_points": "lots"})


def test_hn_hits_map_to_entries_with_item_link_fallback() -> None:
    body = b"""{"hits": [
        {"objectID": "101", "title": "Show HN: a tool", "url": "https://example.com/tool",
         "created_at": "2026-10-06T08:00:00Z", "story_text": null},
        {"objectID": "102", "title": "Ask HN: anything", "url": null,
         "created_at": "2026-10-06T09:00:00Z", "story_text": "<p>Discuss</p>"}
    ]}"""

    first, second = parse_hn(body)

    assert first.ref == "hn:101"
    assert first.link == "https://example.com/tool"
    assert first.published == datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
    assert second.link == f"{HN_ITEM_URL}102"
    assert second.summary == "Discuss"


def test_hn_skips_malformed_hits_without_failing_the_poll() -> None:
    body = b'{"hits": [42, {"objectID": 7, "title": "bad id"}, {"objectID": "9", "title": "ok"}]}'

    (entry,) = parse_hn(body)

    assert entry.ref == "hn:9"


@pytest.mark.parametrize("body", [b"<xml/>", b'{"nope": 1}', b"\xff\xfe"])
def test_hn_rejects_bodies_that_are_not_search_responses(body: bytes) -> None:
    with pytest.raises(FeedParseError):
        parse_hn(body)
