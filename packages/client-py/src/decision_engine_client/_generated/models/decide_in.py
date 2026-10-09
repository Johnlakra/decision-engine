from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.decide_in_sensitivity import DecideInSensitivity, check_decide_in_sensitivity
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.decide_in_questions import DecideInQuestions
    from ..models.decide_in_state_type_1 import DecideInStateType1


T = TypeVar("T", bound="DecideIn")


@_attrs_define
class DecideIn:
    """
    Attributes:
        state (DecideInStateType1 | list[Any] | str):
        explain (bool | Unset):  Default: False.
        language (str | Unset):  Default: 'en'.
        niche (None | str | Unset):
        questions (DecideInQuestions | Unset):
        sensitivity (DecideInSensitivity | Unset):  Default: 'public'.
    """

    state: DecideInStateType1 | list[Any] | str
    explain: bool | Unset = False
    language: str | Unset = "en"
    niche: None | str | Unset = UNSET
    questions: DecideInQuestions | Unset = UNSET
    sensitivity: DecideInSensitivity | Unset = "public"
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.decide_in_state_type_1 import DecideInStateType1  # noqa: PLC0415

        state: dict[str, Any] | list[Any] | str
        if isinstance(self.state, DecideInStateType1):
            state = self.state.to_dict()
        elif isinstance(self.state, list):
            state = self.state

        else:
            state = self.state

        explain = self.explain

        language = self.language

        niche: None | str | Unset
        if isinstance(self.niche, Unset):
            niche = UNSET
        else:
            niche = self.niche

        questions: dict[str, Any] | Unset = UNSET
        if not isinstance(self.questions, Unset):
            questions = self.questions.to_dict()

        sensitivity: str | Unset = UNSET
        if not isinstance(self.sensitivity, Unset):
            sensitivity = self.sensitivity

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "state": state,
            }
        )
        if explain is not UNSET:
            field_dict["explain"] = explain
        if language is not UNSET:
            field_dict["language"] = language
        if niche is not UNSET:
            field_dict["niche"] = niche
        if questions is not UNSET:
            field_dict["questions"] = questions
        if sensitivity is not UNSET:
            field_dict["sensitivity"] = sensitivity

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.decide_in_questions import DecideInQuestions  # noqa: PLC0415
        from ..models.decide_in_state_type_1 import DecideInStateType1  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_state(data: object) -> DecideInStateType1 | list[Any] | str:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                state_type_1 = DecideInStateType1.from_dict(data)

                return state_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                state_type_2 = cast(list[Any], data)

                return state_type_2
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecideInStateType1 | list[Any] | str, data)

        state = _parse_state(d.pop("state"))

        explain = d.pop("explain", UNSET)

        language = d.pop("language", UNSET)

        def _parse_niche(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        niche = _parse_niche(d.pop("niche", UNSET))

        _questions = d.pop("questions", UNSET)
        questions: DecideInQuestions | Unset
        if isinstance(_questions, Unset):
            questions = UNSET
        else:
            questions = DecideInQuestions.from_dict(_questions)

        _sensitivity = d.pop("sensitivity", UNSET)
        sensitivity: DecideInSensitivity | Unset
        if isinstance(_sensitivity, Unset):
            sensitivity = UNSET
        else:
            sensitivity = check_decide_in_sensitivity(_sensitivity)

        decide_in = cls(
            state=state,
            explain=explain,
            language=language,
            niche=niche,
            questions=questions,
            sensitivity=sensitivity,
        )

        decide_in.additional_properties = d
        return decide_in

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
