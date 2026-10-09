from typing import Literal

ExportFeedbackFormat = Literal["laya_eval", "laya_train"]

EXPORT_FEEDBACK_FORMAT_VALUES: set[ExportFeedbackFormat] = {
    "laya_eval",
    "laya_train",
}


def check_export_feedback_format(value: str) -> ExportFeedbackFormat:
    if value in EXPORT_FEEDBACK_FORMAT_VALUES:
        return value
    raise TypeError(f"Unexpected value {value!r}. Expected one of {EXPORT_FEEDBACK_FORMAT_VALUES!r}")
