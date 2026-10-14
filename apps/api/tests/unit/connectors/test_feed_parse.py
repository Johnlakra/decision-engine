"""RSS 2.0 and Atom parsing: fields, cleanup, caps and hostile input (FR-90)."""

from datetime import UTC, datetime

import pytest

from app.connectors.feed_parse import (
    MAX_ENTRIES,
    MAX_REF_CHARS,
    FeedParseError,
    clean_text,
    parse_date,
    parse_feed,
    stable_ref,
)

RSS_BODY = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Demo</title>
  <item>
    <title>Free credits for <b>builders</b></title>
    <link>https://example.com/credits</link>
    <guid>https://example.com/?p=1</guid>
    <description>&lt;p&gt;Apply by &lt;b&gt;30 Nov&lt;/b&gt;.&lt;/p&gt;</description>
    <pubDate>Mon, 05 Oct 2026 09:30:00 GMT</pubDate>
  </item>
  <item>
    <title>No guid falls back to link</title>
    <link>https://example.com/two</link>
  </item>
  <item>
    <link>https://example.com/no-title</link>
  </item>
</channel></rss>"""

ATOM_BODY = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Demo</title>
  <entry>
    <id>tag:example.com,2026:1</id>
    <title>Beta opens</title>
    <link rel="self" href="https://example.com/self"/>
    <link rel="alternate" href="https://example.com/beta"/>
    <summary>Join the waitlist today</summary>
    <updated>2026-10-06T08:00:00Z</updated>
  </entry>
</feed>"""


def test_rss_items_map_to_entries_with_guid_as_ref() -> None:
    entries = parse_feed(RSS_BODY)

    assert [entry.ref for entry in entries] == [
        "https://example.com/?p=1",
        "https://example.com/two",
    ]
    first = entries[0]
    assert first.title == "Free credits for builders"
    assert first.link == "https://example.com/credits"
    assert first.summary == "Apply by 30 Nov ."
    assert first.published == datetime(2026, 10, 5, 9, 30, tzinfo=UTC)


def test_atom_entry_prefers_alternate_link_and_parses_iso_date() -> None:
    (entry,) = parse_feed(ATOM_BODY)

    assert entry.ref == "tag:example.com,2026:1"
    assert entry.link == "https://example.com/beta"
    assert entry.summary == "Join the waitlist today"
    assert entry.published == datetime(2026, 10, 6, 8, 0, tzinfo=UTC)


def test_entries_are_capped_per_poll() -> None:
    items = "".join(
        f"<item><title>t{n}</title><guid>g{n}</guid></item>" for n in range(MAX_ENTRIES + 25)
    )
    body = f"<rss><channel>{items}</channel></rss>".encode()

    assert len(parse_feed(body)) == MAX_ENTRIES


def test_long_ref_is_hashed_to_fit_the_schema_limit() -> None:
    long_guid = "x" * (MAX_REF_CHARS + 50)
    body = f"<rss><channel><item><title>t</title><guid>{long_guid}</guid></item></channel></rss>"

    (entry,) = parse_feed(body.encode())

    assert len(entry.ref) == 64  # sha256 hex
    assert entry.ref == stable_ref(long_guid)


@pytest.mark.parametrize(
    "body",
    [
        b"not xml at all",
        b'<!DOCTYPE rss [<!ENTITY a "aaaa">]><rss>&a;</rss>',  # entity expansion is refused
        b"<html><body>hi</body></html>",
    ],
)
def test_hostile_or_foreign_bodies_raise_parse_error(body: bytes) -> None:
    with pytest.raises(FeedParseError):
        parse_feed(body)


def test_clean_text_strips_tags_unescapes_and_caps() -> None:
    assert clean_text("<p>Hello&nbsp;&amp;  bye</p>") == "Hello & bye"
    assert clean_text("abcdef", limit=3) == "abc"
    assert clean_text(None) == ""


def test_parse_date_rejects_garbage_and_assumes_utc_for_naive_values() -> None:
    assert parse_date("yesterday-ish") is None
    assert parse_date("   ") is None
    assert parse_date("2026-10-06T08:00:00") == datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
