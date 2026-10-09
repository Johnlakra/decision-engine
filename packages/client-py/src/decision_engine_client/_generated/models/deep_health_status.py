from typing import Literal

DeepHealthStatus = Literal["degraded", "ok"]

DEEP_HEALTH_STATUS_VALUES: set[DeepHealthStatus] = {
    "degraded",
    "ok",
}


def check_deep_health_status(value: str) -> DeepHealthStatus:
    if value in DEEP_HEALTH_STATUS_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {DEEP_HEALTH_STATUS_VALUES!r}")
