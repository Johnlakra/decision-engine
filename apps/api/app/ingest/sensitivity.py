"""Item sensitivity at ingest (ADR 0005). First match wins; unknown sources fail closed."""

from typing import Literal

from app.schemas.ingest import Hints

SensitivityValue = Literal["public", "private"]

SOURCE_DEFAULTS: dict[str, SensitivityValue] = {
    "manual": "public",
    "webhook": "public",
    "radar": "public",
    "seed": "public",
    "rss": "public",
    "gmail": "private",
    "instagram": "private",
    "telegram": "private",
    "voice": "private",
}
FALLBACK: SensitivityValue = "private"


def resolve_item_sensitivity(
    source: str,
    hints: Hints | None,
    source_row_sensitivity: str | None = None,
) -> SensitivityValue:
    """hints.sensitivity, then the sources row, then the source-type default."""
    if hints is not None and hints.sensitivity is not None:
        return hints.sensitivity
    if source_row_sensitivity in ("public", "private"):
        return source_row_sensitivity  # type: ignore[return-value]
    return SOURCE_DEFAULTS.get(source, FALLBACK)
