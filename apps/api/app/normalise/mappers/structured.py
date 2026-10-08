"""Mapper for already-structured payloads: {title|subject, body|text|...} or a plain string."""

from collections.abc import Mapping
from typing import Any

from app.normalise.mappers import register_mapper
from app.schemas.content import NormalisedContent

TITLE_CHARS = 120
TITLE_KEYS = ("title", "subject")
BODY_KEYS = ("body", "text", "message", "description")
SENDER_KEYS = ("sender", "from")
URL_KEYS = ("url", "link")


def first_line_title(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:TITLE_CHARS]
    return ""


def _first_str(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


@register_mapper("structured")
def map_structured(
    source: str, payload: Any, hints: Mapping[str, Any] | None
) -> NormalisedContent | None:
    if isinstance(payload, str):
        line = first_line_title(payload)
        return NormalisedContent(title=line, body=payload) if line else None
    if not isinstance(payload, dict):
        return None
    title = _first_str(payload, TITLE_KEYS)
    body = _first_str(payload, BODY_KEYS)
    if title is None and body is None:
        return None
    return NormalisedContent(
        title=(title or first_line_title(body or ""))[:500],
        body=body or "",
        sender=_first_str(payload, SENDER_KEYS),
        url=_first_str(payload, URL_KEYS),
    )
