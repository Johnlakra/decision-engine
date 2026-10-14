from typing import Literal

SettingsOutLanguagesItem = Literal["en", "hi", "pa"]

SETTINGS_OUT_LANGUAGES_ITEM_VALUES: set[SettingsOutLanguagesItem] = {
    "en",
    "hi",
    "pa",
}


def check_settings_out_languages_item(value: str) -> SettingsOutLanguagesItem:
    if value in SETTINGS_OUT_LANGUAGES_ITEM_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {SETTINGS_OUT_LANGUAGES_ITEM_VALUES!r}")
