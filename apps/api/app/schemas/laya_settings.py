"""Rules for writing Laya modes through /v1/settings (ADR 0008).

Pure functions: the route passes the stored JSON and the set of known niche names.
"""

import re
from collections.abc import Collection, Mapping
from typing import Any

from app.schemas.settings import LAYA_BY_NICHE_KEY, LAYA_MODE_KEY, SettingsIn

NICHE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
GATED_TYPE = "https://decision-engine/problems/laya-mode-gated"
GATED_TITLE = "Laya 'on' needs the calibration gate"
GATED_DETAIL = "Switching to 'on' requires the LAYA.md §5 gate and an ADR"
ON = "on"


def _error(field: str, message: str, code: str) -> dict[str, str]:
    return {"field": f"body.{field}", "message": message, "code": code}


def unknown_niche_errors(body: SettingsIn, known: Collection[str]) -> list[dict[str, str]]:
    if LAYA_BY_NICHE_KEY not in body.model_fields_set:
        return []
    return [
        _error(f"{LAYA_BY_NICHE_KEY}.{name}", f"unknown niche {name!r}", "unknown_niche")
        for name in body.laya_mode_by_niche
        if not NICHE_NAME.match(name) or name not in known
    ]


def gated_errors(body: SettingsIn, stored: Mapping[str, Any]) -> list[dict[str, str]]:
    """'on' is accepted only as an unchanged re-send of the stored value."""
    message = "'on' is not available from the API yet"
    errors: list[dict[str, str]] = []
    if (
        LAYA_MODE_KEY in body.model_fields_set
        and body.laya_mode == ON
        and stored.get(LAYA_MODE_KEY) != ON
    ):
        errors.append(_error(LAYA_MODE_KEY, message, "laya_mode_gated"))
    if LAYA_BY_NICHE_KEY in body.model_fields_set:
        stored_map = stored.get(LAYA_BY_NICHE_KEY)
        stored_map = stored_map if isinstance(stored_map, Mapping) else {}
        errors.extend(
            _error(f"{LAYA_BY_NICHE_KEY}.{name}", message, "laya_mode_gated")
            for name, mode in body.laya_mode_by_niche.items()
            if mode == ON and stored_map.get(name) != ON
        )
    return errors


def merge_settings(stored: Mapping[str, Any], body: SettingsIn) -> dict[str, Any]:
    """Stored JSON plus the body. Absent Laya fields keep the stored keys; null/{} delete them."""
    laya_keys = {LAYA_MODE_KEY, LAYA_BY_NICHE_KEY}
    merged = {**stored, **body.model_dump(exclude=laya_keys)}
    if LAYA_MODE_KEY in body.model_fields_set:
        if body.laya_mode is None:
            merged.pop(LAYA_MODE_KEY, None)
        else:
            merged[LAYA_MODE_KEY] = body.laya_mode
    if LAYA_BY_NICHE_KEY in body.model_fields_set:
        if body.laya_mode_by_niche:
            merged[LAYA_BY_NICHE_KEY] = dict(body.laya_mode_by_niche)
        else:
            merged.pop(LAYA_BY_NICHE_KEY, None)
    return merged
