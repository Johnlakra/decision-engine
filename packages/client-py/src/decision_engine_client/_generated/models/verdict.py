from typing import Literal

Verdict = Literal["approve", "edit", "reject", "snooze"]

VERDICT_VALUES: set[Verdict] = {
    "approve",
    "edit",
    "reject",
    "snooze",
}


def check_verdict(value: str) -> Verdict:
    if value in VERDICT_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {VERDICT_VALUES!r}")
