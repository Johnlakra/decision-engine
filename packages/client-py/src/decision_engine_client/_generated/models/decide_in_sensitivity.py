from typing import Literal

DecideInSensitivity = Literal["private", "public"]

DECIDE_IN_SENSITIVITY_VALUES: set[DecideInSensitivity] = {
    "private",
    "public",
}


def check_decide_in_sensitivity(value: str) -> DecideInSensitivity:
    if value in DECIDE_IN_SENSITIVITY_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {DECIDE_IN_SENSITIVITY_VALUES!r}")
