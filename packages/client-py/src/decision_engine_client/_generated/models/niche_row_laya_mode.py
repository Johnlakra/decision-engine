from typing import Literal

NicheRowLayaMode = Literal["off", "on", "shadow"]

NICHE_ROW_LAYA_MODE_VALUES: set[NicheRowLayaMode] = {
    "off",
    "on",
    "shadow",
}


def check_niche_row_laya_mode(value: str) -> NicheRowLayaMode:
    if value in NICHE_ROW_LAYA_MODE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {NICHE_ROW_LAYA_MODE_VALUES!r}")
