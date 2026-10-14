"""Telegram formatting, callback parsing, secret checks and update shapes (FR-43, FR-94)."""

import uuid

import pytest

from app.connectors.telegram_format import (
    CODE_APPROVE,
    callback_data,
    chat_is_allowed,
    parse_callback,
    ping_keyboard,
    ping_text,
)
from app.connectors.telegram_inbound import parse_update, verify_secret
from app.models.enums import Verdict

ITEM_ID = uuid.UUID("0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e")


def test_callback_data_round_trips_and_fits_telegram_limit() -> None:
    data = callback_data(CODE_APPROVE, ITEM_ID)

    parsed = parse_callback(data)

    assert len(data.encode()) <= 64
    assert parsed is not None
    assert parsed.verdict == Verdict.APPROVE
    assert parsed.item_id == ITEM_ID


@pytest.mark.parametrize(
    "data",
    [
        None,
        42,
        "",
        "de:x:0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",  # unknown code
        "de:a:not-a-uuid",
        "other:a:0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",
        "de:a:0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e:extra",
    ],
)
def test_malformed_callback_payloads_are_refused(data: object) -> None:
    assert parse_callback(data) is None


def test_ping_text_escapes_remote_strings_and_drops_unsafe_links() -> None:
    text = ping_text(
        {"title": "<img src=x onerror=alert(1)> Credits & more"},
        {"rationale": "Apply <b>now</b>"},
        "javascript:alert(1)",
    )

    assert "<img" not in text
    assert "&lt;img" in text
    assert "&amp; more" in text
    assert "&lt;b&gt;now" in text
    assert "javascript" not in text


def test_ping_text_keeps_https_links_and_has_a_fallback_title() -> None:
    assert "https://example.com/launch" in ping_text(None, None, "https://example.com/launch")
    assert ping_text(None, None, None).startswith("<b>New item</b>")


def test_keyboard_has_approve_and_reject_buttons_for_the_item() -> None:
    (row,) = ping_keyboard(ITEM_ID)

    assert [button["text"] for button in row] == ["Save and act", "Not interested"]
    assert all(parse_callback(button["callback_data"]) is not None for button in row)


def test_chat_allow_list_fails_closed_when_empty() -> None:
    assert chat_is_allowed(111, ["111"]) is True
    assert chat_is_allowed(222, ["111"]) is False
    assert chat_is_allowed(111, []) is False


@pytest.mark.parametrize(
    ("header", "expected", "accepted"),
    [
        ("s3cret", "s3cret", True),
        ("wrong", "s3cret", False),
        (None, "s3cret", False),
        ("anything", "", False),  # unset secret never accepts
    ],
)
def test_webhook_secret_is_checked_and_fails_closed(
    header: str | None, expected: str, accepted: bool
) -> None:
    assert verify_secret(header, expected) is accepted


def test_update_with_unexpected_shape_is_ignored_not_fatal() -> None:
    assert parse_update({"update_id": "not-a-number"}) is None
    update = parse_update({"update_id": 1, "message": {"message_id": 2, "chat": {"id": 3}}})
    assert update is not None and update.message is not None
