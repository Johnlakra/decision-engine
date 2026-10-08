"""ADR 0005: item sensitivity at ingest (FR-01, FR-06)."""

import pytest

from app.ingest.sensitivity import resolve_item_sensitivity
from app.schemas.ingest import Hints


@pytest.mark.parametrize("source", ["manual", "webhook", "radar", "seed", "rss"])
def test_own_app_sources_default_public(source: str) -> None:
    assert resolve_item_sensitivity(source, None) == "public"


@pytest.mark.parametrize("source", ["gmail", "instagram", "telegram", "voice"])
def test_personal_message_sources_default_private(source: str) -> None:
    assert resolve_item_sensitivity(source, None) == "private"


@pytest.mark.parametrize("source", ["csv", "my-crm", "unknown_thing"])
def test_unknown_sources_fail_closed(source: str) -> None:
    assert resolve_item_sensitivity(source, None) == "private"


def test_hint_beats_source_row_and_default() -> None:
    hints = Hints(sensitivity="public")
    assert resolve_item_sensitivity("gmail", hints, "private") == "public"
    assert resolve_item_sensitivity("manual", Hints(sensitivity="private"), "public") == "private"


def test_source_row_beats_default() -> None:
    assert resolve_item_sensitivity("manual", None, "private") == "private"
    assert resolve_item_sensitivity("gmail", Hints(), "public") == "public"


def test_hints_without_sensitivity_fall_through() -> None:
    assert resolve_item_sensitivity("webhook", Hints(title="x")) == "public"
