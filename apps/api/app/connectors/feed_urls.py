"""Feed source types and the URL each one polls (FR-90, docs/CONNECTORS.md).

A source row stores only its ``config``; the poll URL is derived here so the stored value is
the human input (a feed URL or a search query), never a URL built from model output.
"""

from typing import Any
from urllib.parse import urlencode

from app.connectors.feed_parse import clean_text

TYPE_RSS = "rss"
TYPE_GOOGLE_NEWS = "google_news"
TYPE_HN = "hn"
FEED_TYPES = frozenset({TYPE_RSS, TYPE_GOOGLE_NEWS, TYPE_HN})

GOOGLE_NEWS_BASE = "https://news.google.com/rss/search"
HN_SEARCH_BASE = "https://hn.algolia.com/api/v1/search_by_date"
MAX_QUERY_CHARS = 200
DEFAULT_HN_MIN_POINTS = 50
MAX_HN_MIN_POINTS = 10_000


class FeedConfigError(ValueError):
    """A source row whose config cannot produce a poll URL. The poll records it as an error."""


def _required_text(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FeedConfigError(f"config.{key} must be a non-empty string")
    return value.strip()


def google_news_url(query: str) -> str:
    """India-edition Google News RSS search (docs/CONNECTORS.md)."""
    cleaned = clean_text(query, MAX_QUERY_CHARS)
    if not cleaned:
        raise FeedConfigError("config.query must not be empty")
    params = {"q": cleaned, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    return f"{GOOGLE_NEWS_BASE}?{urlencode(params)}"


def hn_search_url(min_points: int = DEFAULT_HN_MIN_POINTS) -> str:
    """Hacker News stories newest first, above a points floor (Algolia search API)."""
    if not 0 <= min_points <= MAX_HN_MIN_POINTS:
        raise FeedConfigError("config.min_points out of range")
    params = {"tags": "story", "numericFilters": f"points>{min_points}"}
    return f"{HN_SEARCH_BASE}?{urlencode(params)}"


def feed_url(feed_type: str, config: dict[str, Any]) -> str:
    """The URL to poll for a source of ``feed_type``. Raises FeedConfigError when unusable."""
    if feed_type == TYPE_RSS:
        return _required_text(config, "url")
    if feed_type == TYPE_GOOGLE_NEWS:
        return google_news_url(_required_text(config, "query"))
    if feed_type == TYPE_HN:
        min_points = config.get("min_points", DEFAULT_HN_MIN_POINTS)
        if not isinstance(min_points, int) or isinstance(min_points, bool):
            raise FeedConfigError("config.min_points must be an integer")
        return hn_search_url(min_points)
    raise FeedConfigError(f"unsupported feed type {feed_type!r}")
