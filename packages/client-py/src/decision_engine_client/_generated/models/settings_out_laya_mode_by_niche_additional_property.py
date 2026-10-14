from typing import Literal

SettingsOutLayaModeByNicheAdditionalProperty = Literal["off", "on", "shadow"]

SETTINGS_OUT_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES: set[SettingsOutLayaModeByNicheAdditionalProperty] = {
    "off",
    "on",
    "shadow",
}


def check_settings_out_laya_mode_by_niche_additional_property(
    value: str,
) -> SettingsOutLayaModeByNicheAdditionalProperty:
    if value in SETTINGS_OUT_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES:
        return value
    raise TypeError(
        f"Unexpected value {value!r}. Expected one of {SETTINGS_OUT_LAYA_MODE_BY_NICHE_ADDITIONAL_PROPERTY_VALUES!r}"
    )
