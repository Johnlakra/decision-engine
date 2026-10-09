from typing import Literal

DecisionResultStatus = Literal["acting", "done", "rejected", "snoozed"]

DECISION_RESULT_STATUS_VALUES: set[DecisionResultStatus] = {
    "acting",
    "done",
    "rejected",
    "snoozed",
}


def check_decision_result_status(value: str) -> DecisionResultStatus:
    if value in DECISION_RESULT_STATUS_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {DECISION_RESULT_STATUS_VALUES!r}")
