from typing import Literal

SettingsInLayaModeByNicheAdditionalProperty = Literal["off", "on", "shadow"]

SETTINGS_IN_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES: set[SettingsInLayaModeByNicheAdditionalProperty] = {
    "off",
    "on",
    "shadow",
}


def check_settings_in_laya_mode_by_niche_additional_property(value: str) -> SettingsInLayaModeByNicheAdditionalProperty:
    if value in SETTINGS_IN_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {SETTINGS_IN_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES!r}"
    )
