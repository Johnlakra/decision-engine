"""Laya mode resolution: per-niche override > tenant setting > env default (FR-23, FR-24)."""

from collections.abc import Mapping
from typing import Any, Literal, get_args

Mode = Literal["off", "shadow", "on"]
MODES: frozenset[str] = frozenset(get_args(Mode))
SAFE_DEFAULT: Mode = "shadow"


def _valid(value: Any) -> Mode | None:
    return value if isinstance(value, str) and value in MODES else None  # type: ignore[return-value]


def resolve_mode(tenant_settings: Mapping[str, Any], niche: str | None, default: str) -> Mode:
    """Invalid values are ignored; the final fallback is `shadow`, never `on`."""
    overrides = tenant_settings.get("laya_mode_by_niche")
    if niche and isinstance(overrides, Mapping) and (mode := _valid(overrides.get(niche))):
        return mode
    return _valid(tenant_settings.get("laya_mode")) or _valid(default) or SAFE_DEFAULT


def has_active_override(tenant_settings: Mapping[str, Any]) -> bool:
    """True when some niche override is not `off` (Laya may be consulted for it)."""
    overrides = tenant_settings.get("laya_mode_by_niche")
    if not isinstance(overrides, Mapping):
        return False
    return any(_valid(v) in ("shadow", "on") for v in overrides.values())
