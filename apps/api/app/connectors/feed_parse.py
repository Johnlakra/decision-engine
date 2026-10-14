"""Parse RSS 2.0 and Atom feeds into entries (FR-90). Pure: bytes in, entries out.

Namespaces are ignored on purpose: feeds in the wild mix ``content:encoded``, ``media:*`` and
``dc:*``, and only the local element names matter here. ``defusedxml`` rejects entity bombs.
"""

import hashlib
import html
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from defusedxml import ElementTree as SafeET

MAX_ENTRIES = 100  # per poll; keeps one feed from flooding the queue
MAX_SUMMARY_CHARS = 4000
MAX_TITLE_CHARS = 500
MAX_REF_CHARS = 300  # matches IngestItemIn.source_ref max_length
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


class FeedParseError(ValueError):
    """The body is not a feed we understand. Callers record it; nothing is ingested."""


@dataclass(frozen=True)
class FeedEntry:
    ref: str
    title: str
    link: str | None
    summary: str
    published: datetime | None


def clean_text(raw: str | None, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Strip tags, unescape entities, collapse whitespace, cap length."""
    if not raw:
        return ""
    unescaped = html.unescape(_TAG.sub(" ", raw))
    return _SPACE.sub(" ", unescaped).strip()[:limit]


def stable_ref(raw: str) -> str:
    """A source_ref that fits the schema limit; long ids are hashed, not truncated."""
    if len(raw) <= MAX_REF_CHARS:
        return raw
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_date(raw: str | None) -> datetime | None:
    """RFC 822 (RSS) or ISO 8601 (Atom). Unparseable dates are dropped, not guessed."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed: datetime | None = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _child_text(element: Any, names: tuple[str, ...]) -> str | None:
    for child in element:
        if _local(child.tag) in names:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return None


def _atom_link(element: Any) -> str | None:
    fallback: str | None = None
    for child in element:
        if _local(child.tag) != "link":
            continue
        href: str | None = child.get("href")
        if not href or not href.strip():
            continue
        if child.get("rel", "alternate") == "alternate":
            return href.strip()
        fallback = fallback or href.strip()
    return fallback


def _entry_from_rss(item: Any) -> FeedEntry | None:
    link = _child_text(item, ("link",))
    ref = _child_text(item, ("guid",)) or link
    title = clean_text(_child_text(item, ("title",)), MAX_TITLE_CHARS)
    if not ref or not title:
        return None
    summary = clean_text(_child_text(item, ("description", "encoded", "summary")))
    published = parse_date(_child_text(item, ("pubDate", "published", "updated")))
    return FeedEntry(stable_ref(ref), title, link, summary, published)


def _entry_from_atom(entry: Any) -> FeedEntry | None:
    link = _atom_link(entry)
    ref = _child_text(entry, ("id",)) or link
    title = clean_text(_child_text(entry, ("title",)), MAX_TITLE_CHARS)
    if not ref or not title:
        return None
    summary = clean_text(_child_text(entry, ("summary", "content")))
    published = parse_date(_child_text(entry, ("published", "updated")))
    return FeedEntry(stable_ref(ref), title, link, summary, published)


def _elements(root: Any, local_name: str) -> Iterator[Any]:
    return (element for element in root.iter() if _local(element.tag) == local_name)


def parse_feed(body: bytes) -> list[FeedEntry]:
    """RSS 2.0 or Atom bytes -> at most ``MAX_ENTRIES`` entries, in feed order."""
    try:
        root = SafeET.fromstring(body)
    except SyntaxError as exc:  # ElementTree's ParseError subclasses SyntaxError
        raise FeedParseError("body is not well-formed XML") from exc
    except Exception as exc:  # defusedxml raises its own DTD/entity errors
        raise FeedParseError("body rejected by the XML parser") from exc
    root_name = _local(root.tag)
    raw_entries: Iterator[Any]
    build: Callable[[Any], FeedEntry | None]
    if root_name == "rss":
        raw_entries, build = _elements(root, "item"), _entry_from_rss
    elif root_name == "feed":
        raw_entries, build = _elements(root, "entry"), _entry_from_atom
    else:
        raise FeedParseError(f"unsupported feed root <{root_name}>")
    entries: list[FeedEntry] = []
    for raw in raw_entries:
        entry = build(raw)
        if entry is not None:
            entries.append(entry)
        if len(entries) >= MAX_ENTRIES:
            break
    return entries
