"""Mapper registry: deterministic payload -> NormalisedContent, no LLM (FR-10, FR-11)."""

from collections.abc import Callable, Mapping
from typing import Any

from app.schemas.content import NormalisedContent

Mapper = Callable[[str, Any, Mapping[str, Any] | None], NormalisedContent | None]

_MAPPERS: dict[str, tuple[Mapper, tuple[str, ...] | None]] = {}  # insertion order = priority


def register_mapper(
    name: str, *, sources: tuple[str, ...] | None = None
) -> Callable[[Mapper], Mapper]:
    """Register a mapper. `sources` limits it to those item sources (None = every source)."""

    def deco(fn: Mapper) -> Mapper:
        _MAPPERS[name] = (fn, sources)
        return fn

    return deco


def map_payload(
    source: str, payload: Any, hints: Mapping[str, Any] | None
) -> NormalisedContent | None:
    """First mapper that recognises the payload wins; None means 'ask the LLM'."""
    for fn, sources in list(_MAPPERS.values()):
        if sources is not None and source not in sources:
            continue
        content = fn(source, payload, hints)
        if content is not None:
            return content
    return None


from app.normalise.mappers import hints as _hints  # noqa: E402,F401
from app.normalise.mappers import structured as _structured  # noqa: E402,F401
