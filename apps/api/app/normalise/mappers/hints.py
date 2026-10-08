"""Mapper for items whose sender supplied title/body hints."""

from collections.abc import Mapping
from typing import Any

from app.normalise.mappers import register_mapper
from app.normalise.mappers.structured import first_line_title
from app.schemas.content import MAX_TITLE, NormalisedContent


@register_mapper("hints")
def map_hints(
    source: str, payload: Any, hints: Mapping[str, Any] | None
) -> NormalisedContent | None:
    if not hints:
        return None
    title, body = hints.get("title"), hints.get("body")
    if not (title or body):
        return None
    body_text = body or ""
    return NormalisedContent(
        title=(title or first_line_title(body_text))[:MAX_TITLE],
        body=body_text,
        url=hints.get("url"),
        sender=hints.get("sender"),
    )
