from typing import Literal

AnswerSource = Literal["hint", "human", "laya", "llm_fallback"]

ANSWER_SOURCE_VALUES: set[AnswerSource] = {
    "hint",
    "human",
    "laya",
    "llm_fallback",
}


def check_answer_source(value: str) -> AnswerSource:
    if value in ANSWER_SOURCE_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {ANSWER_SOURCE_VALUES!r}")
