"""Tenant settings: ``GET`` and ``PUT /v1/settings`` (FR-43, UI_UX Settings screen).

The stored JSON is untrusted, so reads go through the same validators the notifier uses, and
anything invalid falls back to a default. Writes must pass the strict model below.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.connectors.notify_policy import MAX_PING_CAP_PER_DAY, settings_from

Language = Literal["en", "hi", "pa"]
LANGUAGE_VALUES: tuple[Language, ...] = ("en", "hi", "pa")
DEFAULT_LANGUAGES: tuple[Language, ...] = ("en",)
MAX_INTERESTS = 20
MAX_INTEREST_CHARS = 60
MAX_LANGUAGES = 3
Interest = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_INTEREST_CHARS)
]


class SettingsOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "quiet_hours": [22, 7],
                    "digest_hour": 8,
                    "ping_cap_per_day": 3,
                    "interests": ["ai", "crypto"],
                    "languages": ["en"],
                }
            ]
        }
    )

    quiet_hours: list[int]
    digest_hour: int
    ping_cap_per_day: int
    interests: list[str]
    languages: list[Language]


class SettingsIn(BaseModel):
    """Full replacement of the editable settings. Unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")

    quiet_hours: list[int] = Field(min_length=2, max_length=2)
    digest_hour: int = Field(ge=0, le=23)
    ping_cap_per_day: int = Field(ge=0, le=MAX_PING_CAP_PER_DAY)
    interests: list[Interest] = Field(max_length=MAX_INTERESTS)
    languages: list[Language] = Field(min_length=1, max_length=MAX_LANGUAGES)

    @field_validator("quiet_hours")
    @classmethod
    def _hours_in_range(cls, value: list[int]) -> list[int]:
        if any(hour < 0 or hour > 23 for hour in value):
            raise ValueError("quiet hours must be between 0 and 23")
        return value


def _languages_from(raw: dict[str, Any]) -> tuple[Language, ...]:
    value = raw.get("languages")
    if not isinstance(value, list):
        return DEFAULT_LANGUAGES
    kept = tuple(lang for lang in LANGUAGE_VALUES if lang in value)
    return kept or DEFAULT_LANGUAGES


def _interests_from(raw: dict[str, Any]) -> list[str]:
    value = raw.get("interests")
    if not isinstance(value, list):
        return []
    cleaned = [item.strip()[:MAX_INTEREST_CHARS] for item in value if isinstance(item, str)]
    return [item for item in cleaned if item][:MAX_INTERESTS]


def settings_out(raw: dict[str, Any] | None) -> SettingsOut:
    """Validated view of the stored settings, with defaults for anything missing or invalid."""
    source = raw or {}
    current = settings_from(source)
    return SettingsOut(
        quiet_hours=list(current.quiet_hours),
        digest_hour=current.digest_hour,
        ping_cap_per_day=current.ping_cap_per_day,
        interests=_interests_from(source),
        languages=list(_languages_from(source)),
    )
