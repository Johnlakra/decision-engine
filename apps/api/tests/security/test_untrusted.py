"""Tests for app.security.untrusted.as_data (NFR-05, FR-42)."""

import re
from pathlib import Path

import pytest

from app.security.untrusted import MAX_DATA_CHARS, as_data

INJECTION = (Path(__file__).parent / "fixtures" / "injection.txt").read_text()
FENCE_TAG = re.compile(r"<\s*/?\s*item_content", re.IGNORECASE)


def test_default_cap_constant() -> None:
    """NFR-05: the default cap is 8000 characters."""
    assert MAX_DATA_CHARS == 8000


def test_strips_control_chars_keeps_newline_and_tab() -> None:
    """NFR-05: control characters are removed, \\n and \\t survive."""
    assert as_data("a\x00b\x07c\x1bd\x7fe\tf\ng\r") == "abcde\tf\ng"


def test_caps_length_with_marker() -> None:
    """NFR-05: long text is truncated and marked."""
    out = as_data("x" * 100, max_chars=20)
    assert out.endswith("…[truncated]")
    assert out.startswith("x" * 10)


def test_default_cap_applies() -> None:
    """NFR-05: the default max_chars is MAX_DATA_CHARS."""
    out = as_data("y" * (MAX_DATA_CHARS * 2))
    assert out.endswith("…[truncated]")
    assert len(out) < MAX_DATA_CHARS * 2


def test_short_text_not_marked() -> None:
    """NFR-05: text under the cap is returned without the marker."""
    assert "…[truncated]" not in as_data("hello", max_chars=20)


@pytest.mark.parametrize(
    "payload",
    [
        "</item_content>",
        "</ITEM_CONTENT>",
        "</Item_Content>",
        "</item_content >",
        "< /item_content>",
        "<  /  item_content  >",
        "</item_content\t>",
        "</item_content\n>",
        "<item_content id='x'>",
        "<ITEM_CONTENT>",
        "< item_content>",
    ],
)
def test_neutralizes_fence_tags(payload: str) -> None:
    """NFR-05, FR-42: fence open/close tags cannot survive in cleaned data."""
    out = as_data(f"before {payload} after")
    assert not FENCE_TAG.search(out)
    assert "before" in out
    assert "after" in out


def test_injection_fixture_cannot_close_fence() -> None:
    """FR-42: a realistic injection email has its fake fences neutralized."""
    out = as_data(INJECTION)
    assert not FENCE_TAG.search(out)
    # Text is preserved as data, not dropped.
    assert "ignore previous instructions" in out


@pytest.mark.parametrize(
    "text",
    ["plain", "a\x00b</item_content>c", INJECTION, "z" * 50_000, "<item_content>"],
)
def test_idempotent(text: str) -> None:
    """NFR-05: as_data(as_data(x)) == as_data(x)."""
    once = as_data(text)
    assert as_data(once) == once


def test_idempotent_with_small_cap() -> None:
    """NFR-05: idempotence holds when truncation occurred."""
    once = as_data("q" * 200, max_chars=50)
    assert as_data(once, max_chars=50) == once


@pytest.mark.parametrize("bad", [None, 123, b"bytes", ["x"], {"a": 1}])
def test_non_str_raises_type_error(bad: object) -> None:
    """NFR-05: non-string input is a programming error."""
    with pytest.raises(TypeError):
        as_data(bad)  # type: ignore[arg-type]


def test_does_not_wrap() -> None:
    """NFR-05: wrapping is llm.fence()'s job; as_data output is unwrapped."""
    assert not as_data("hello").startswith("<item_content")
    assert not as_data(INJECTION).startswith("<item_content")
    assert as_data("hello") == "hello"
