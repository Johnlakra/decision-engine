from typing import Literal

SettingsOutLayaModeDefault = Literal["off", "on", "shadow"]

SETTINGS_OUT_LAYA_MODE_DEFAULT_VALUES: set[SettingsOutLayaModeDefault] = {
    "off",
    "on",
    "shadow",
}


def check_settings_out_laya_mode_default(value: str) -> SettingsOutLayaModeDefault:
    if value in SETTINGS_OUT_LAYA_MODE_DEFAULT_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {SETTINGS_OUT_LAYA_MODE_DEFAULT_VALUES!r}")
