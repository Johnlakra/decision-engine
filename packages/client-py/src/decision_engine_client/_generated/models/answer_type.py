from typing import Literal

AnswerType = Literal["choice", "noul", "score"]

ANSWER_TYPE_VALUES: set[AnswerType] = {
    "choice",
    "noul",
    "score",
}


def check_answer_type(value: str) -> AnswerType:
    if value in ANSWER_TYPE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {ANSWER_TYPE_VALUES!r}")
