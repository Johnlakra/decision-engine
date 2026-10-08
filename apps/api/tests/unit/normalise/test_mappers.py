"""Mapper registry and the built-in hints and structured mappers (FR-10, FR-11)."""

from app.normalise.mappers import map_payload, register_mapper


def test_hints_mapper_wins_with_title_and_body() -> None:
    out = map_payload("manual", {"x": 1}, {"title": "T", "body": "B", "url": "https://a.io"})
    assert out is not None
    assert (out.title, out.body, out.url) == ("T", "B", "https://a.io")


def test_hints_body_only_derives_title() -> None:
    out = map_payload("manual", {"x": 1}, {"body": "First line\nrest"})
    assert out is not None and out.title == "First line"


def test_school_erp_text_dict_uses_structured_mapper() -> None:
    out = map_payload("manual", {"text": "We are building a school ERP.\nMore."}, None)
    assert out is not None
    assert out.title == "We are building a school ERP."
    assert out.body.startswith("We are building")


def test_structured_subject_message_sender() -> None:
    out = map_payload("email", {"subject": "Hi", "message": "Body", "from": "a@b.c"}, None)
    assert out is not None
    assert (out.title, out.body, out.sender) == ("Hi", "Body", "a@b.c")


def test_plain_string_first_line_is_title() -> None:
    out = map_payload("manual", "Short title\nlong body here", None)
    assert out is not None and out.title == "Short title"
    assert out.body == "Short title\nlong body here"


def test_long_first_line_truncated_to_120() -> None:
    out = map_payload("manual", "x" * 300, None)
    assert out is not None and len(out.title) == 120


def test_unknown_payload_returns_none() -> None:
    assert map_payload("webhook", {"event": "ping", "n": 3}, None) is None
    assert map_payload("webhook", [1, 2], None) is None
    assert map_payload("webhook", "   ", None) is None


def test_non_string_fields_ignored() -> None:
    assert map_payload("webhook", {"text": {"nested": 1}}, None) is None


def test_source_specific_mapper_registered() -> None:
    @register_mapper("unit_test_src", sources=("unit_src",))
    def _m(source, payload, hints):  # type: ignore[no-untyped-def]
        from app.schemas.content import NormalisedContent

        return NormalisedContent(title="custom")

    try:
        out = map_payload("unit_src", {"x": 1}, None)
        assert out is not None and out.title == "custom"
        assert map_payload("other", {"x": 1}, None) is None
    finally:
        from app.normalise.mappers import _MAPPERS

        _MAPPERS.pop("unit_test_src", None)
