"""Parse the Hacker News Algolia search response into feed entries (FR-90). Pure.

The body is untrusted JSON: every field is type-checked and anything malformed is skipped.
"""

import json
from typing import Any

from app.connectors.feed_parse import (
    MAX_ENTRIES,
    MAX_TITLE_CHARS,
    FeedEntry,
    FeedParseError,
    clean_text,
    parse_date,
)

HN_ITEM_URL = "https://news.ycombinator.com/item?id="
MAX_STORY_TEXT_CHARS = 4000


def _text(value: object, limit: int) -> str:
    return clean_text(value, limit) if isinstance(value, str) else ""


def _entry(hit: dict[str, Any]) -> FeedEntry | None:
    object_id = hit.get("objectID")
    title = _text(hit.get("title"), MAX_TITLE_CHARS)
    if not isinstance(object_id, str) or not object_id.strip() or not title:
        return None
    key = object_id.strip()
    external = hit.get("url")
    created = hit.get("created_at")
    link = external if isinstance(external, str) and external.startswith("https://") else None
    return FeedEntry(
        ref=f"hn:{key}",
        title=title,
        link=link or f"{HN_ITEM_URL}{key}",
        summary=_text(hit.get("story_text"), MAX_STORY_TEXT_CHARS),
        published=parse_date(created if isinstance(created, str) else None),
    )


def parse_hn(body: bytes) -> list[FeedEntry]:
    """Algolia ``{"hits": [...]}`` -> entries, capped at ``MAX_ENTRIES``."""
    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedParseError("body is not valid JSON") from exc
    hits = document.get("hits") if isinstance(document, dict) else None
    if not isinstance(hits, list):
        raise FeedParseError("body has no hits list")
    entries: list[FeedEntry] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        entry = _entry(hit)
        if entry is not None:
            entries.append(entry)
        if len(entries) >= MAX_ENTRIES:
            break
    return entries
