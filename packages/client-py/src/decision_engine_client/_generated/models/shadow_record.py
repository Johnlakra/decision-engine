from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.shadow_record_answers_type_0 import ShadowRecordAnswersType0


T = TypeVar("T", bound="ShadowRecord")


@_attrs_define
class ShadowRecord:
    """
    Attributes:
        answers (None | ShadowRecordAnswersType0 | Unset):
        error (None | str | Unset):
        latency_ms (int | None | Unset):
        model (None | str | Unset):
    """

    answers: None | ShadowRecordAnswersType0 | Unset = UNSET
    error: None | str | Unset = UNSET
    latency_ms: int | None | Unset = UNSET
    model: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.shadow_record_answers_type_0 import ShadowRecordAnswersType0  # noqa: PLC0415

        answers: dict[str, Any] | None | Unset
        if isinstance(self.answers, Unset):
            answers = UNSET
        elif isinstance(self.answers, ShadowRecordAnswersType0):
            answers = self.answers.to_dict()
        else:
            answers = self.answers

        error: None | str | Unset
        if isinstance(self.error, Unset):
            error = UNSET
        else:
            error = self.error

        latency_ms: int | None | Unset
        if isinstance(self.latency_ms, Unset):
            latency_ms = UNSET
        else:
            latency_ms = self.latency_ms

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if answers is not UNSET:
            field_dict["answers"] = answers
        if error is not UNSET:
            field_dict["error"] = error
        if latency_ms is not UNSET:
            field_dict["latency_ms"] = latency_ms
        if model is not UNSET:
            field_dict["model"] = model

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.shadow_record_answers_type_0 import ShadowRecordAnswersType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_answers(data: object) -> None | ShadowRecordAnswersType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                answers_type_0 = ShadowRecordAnswersType0.from_dict(data)

                return answers_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ShadowRecordAnswersType0 | Unset, data)

        answers = _parse_answers(d.pop("answers", UNSET))

        def _parse_error(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        error = _parse_error(d.pop("error", UNSET))

        def _parse_latency_ms(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        latency_ms = _parse_latency_ms(d.pop("latency_ms", UNSET))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        shadow_record = cls(
            answers=answers,
            error=error,
            latency_ms=latency_ms,
            model=model,
        )

        shadow_record.additional_properties = d
        return shadow_record

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
