from typing import Literal

NicheRowAutonomy = Literal["ask", "auto", "suggest"]

NICHE_ROW_AUTONOMY_VALUES: set[NicheRowAutonomy] = {
    "ask",
    "auto",
    "suggest",
}


def check_niche_row_autonomy(value: str) -> NicheRowAutonomy:
    if value in NICHE_ROW_AUTONOMY_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {NICHE_ROW_AUTONOMY_VALUES!r}")
