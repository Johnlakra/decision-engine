from typing import Literal

NicheDetailSource = Literal["db", "yaml"]

NICHE_DETAIL_SOURCE_VALUES: set[NicheDetailSource] = {
    "db",
    "yaml",
}


def check_niche_detail_source(value: str) -> NicheDetailSource:
    if value in NICHE_DETAIL_SOURCE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {NICHE_DETAIL_SOURCE_VALUES!r}")
