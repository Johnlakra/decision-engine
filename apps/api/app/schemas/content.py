"""NormalisedContent: the shape of ``items.content`` (C1, FR-10)."""

from typing import Any

from pydantic import BaseModel, Field

MAX_TITLE = 500


class NormalisedContent(BaseModel):
    title: str = Field(max_length=MAX_TITLE)
    body: str = ""
    summary: str | None = None
    sender: str | None = None
    url: str | None = None
    language: str | None = None
    entities: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)  # e.g. "normalise_failed"
