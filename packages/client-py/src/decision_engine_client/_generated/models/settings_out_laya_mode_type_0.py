from typing import Literal

SettingsOutLayaModeType0 = Literal["off", "on", "shadow"]

SETTINGS_OUT_LAYA_MODE_TYPE_0_VALUES: set[SettingsOutLayaModeType0] = {
    "off",
    "on",
    "shadow",
}


def check_settings_out_laya_mode_type_0(value: str) -> SettingsOutLayaModeType0:
    if value in SETTINGS_OUT_LAYA_MODE_TYPE_0_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {SETTINGS_OUT_LAYA_MODE_TYPE_0_VALUES!r}")
