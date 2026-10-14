from typing import Literal

NicheRowSource = Literal["db", "yaml"]

NICHE_ROW_SOURCE_VALUES: set[NicheRowSource] = {
    "db",
    "yaml",
}


def check_niche_row_source(value: str) -> NicheRowSource:
    if value in NICHE_ROW_SOURCE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {NICHE_ROW_SOURCE_VALUES!r}")
