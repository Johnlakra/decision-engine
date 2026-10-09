from typing import Literal

HintsSensitivityType0 = Literal["private", "public"]

HINTS_SENSITIVITY_TYPE_0_VALUES: set[HintsSensitivityType0] = {
    "private",
    "public",
}


def check_hints_sensitivity_type_0(value: str) -> HintsSensitivityType0:
    if value in HINTS_SENSITIVITY_TYPE_0_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {HINTS_SENSITIVITY_TYPE_0_VALUES!r}")
