from typing import Literal

SettingsInLayaModeType0 = Literal["off", "on", "shadow"]

SETTINGS_IN_LAYA_MODE_TYPE_0_VALUES: set[SettingsInLayaModeType0] = {
    "off",
    "on",
    "shadow",
}


def check_settings_in_laya_mode_type_0(value: str) -> SettingsInLayaModeType0:
    if value in SETTINGS_IN_LAYA_MODE_TYPE_0_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {SETTINGS_IN_LAYA_MODE_TYPE_0_VALUES!r}")
