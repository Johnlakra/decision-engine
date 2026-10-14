from typing import Literal

SettingsInLanguagesItem = Literal["en", "hi", "pa"]

SETTINGS_IN_LANGUAGES_ITEM_VALUES: set[SettingsInLanguagesItem] = {
    "en",
    "hi",
    "pa",
}


def check_settings_in_languages_item(value: str) -> SettingsInLanguagesItem:
    if value in SETTINGS_IN_LANGUAGES_ITEM_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {SETTINGS_IN_LANGUAGES_ITEM_VALUES!r}")
