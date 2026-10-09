from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.answer_source import AnswerSource, check_answer_source
from ..models.answer_type import AnswerType, check_answer_type
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.answer_probabilities import AnswerProbabilities


T = TypeVar("T", bound="Answer")


@_attrs_define
class Answer:
    """
    Attributes:
        source (AnswerSource):
        type_ (AnswerType):
        choice (None | str | Unset):
        confidence (float | None | Unset):
        level (int | None | Unset):
        noul (float | None | Unset):
        probabilities (AnswerProbabilities | Unset):
        score (float | None | Unset):
    """

    source: AnswerSource
    type_: AnswerType
    choice: None | str | Unset = UNSET
    confidence: float | None | Unset = UNSET
    level: int | None | Unset = UNSET
    noul: float | None | Unset = UNSET
    probabilities: AnswerProbabilities | Unset = UNSET
    score: float | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source: str = self.source

        type_: str = self.type_

        choice: None | str | Unset
        if isinstance(self.choice, Unset):
            choice = UNSET
        else:
            choice = self.choice

        confidence: float | None | Unset
        if isinstance(self.confidence, Unset):
            confidence = UNSET
        else:
            confidence = self.confidence

        level: int | None | Unset
        if isinstance(self.level, Unset):
            level = UNSET
        else:
            level = self.level

        noul: float | None | Unset
        if isinstance(self.noul, Unset):
            noul = UNSET
        else:
            noul = self.noul

        probabilities: dict[str, Any] | Unset = UNSET
        if not isinstance(self.probabilities, Unset):
            probabilities = self.probabilities.to_dict()

        score: float | None | Unset
        if isinstance(self.score, Unset):
            score = UNSET
        else:
            score = self.score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "type": type_,
            }
        )
        if choice is not UNSET:
            field_dict["choice"] = choice
        if confidence is not UNSET:
            field_dict["confidence"] = confidence
        if level is not UNSET:
            field_dict["level"] = level
        if noul is not UNSET:
            field_dict["noul"] = noul
        if probabilities is not UNSET:
            field_dict["probabilities"] = probabilities
        if score is not UNSET:
            field_dict["score"] = score

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.answer_probabilities import AnswerProbabilities  # noqa: PLC0415

        d = dict(src_dict)
        source = check_answer_source(d.pop("source"))

        type_ = check_answer_type(d.pop("type"))

        def _parse_choice(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        choice = _parse_choice(d.pop("choice", UNSET))

        def _parse_confidence(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        confidence = _parse_confidence(d.pop("confidence", UNSET))

        def _parse_level(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        level = _parse_level(d.pop("level", UNSET))

        def _parse_noul(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        noul = _parse_noul(d.pop("noul", UNSET))

        _probabilities = d.pop("probabilities", UNSET)
        probabilities: AnswerProbabilities | Unset
        if isinstance(_probabilities, Unset):
            probabilities = UNSET
        else:
            probabilities = AnswerProbabilities.from_dict(_probabilities)

        def _parse_score(data: object) -> float | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(float | None | Unset, data)

        score = _parse_score(d.pop("score", UNSET))

        answer = cls(
            source=source,
            type_=type_,
            choice=choice,
            confidence=confidence,
            level=level,
            noul=noul,
            probabilities=probabilities,
            score=score,
        )

        answer.additional_properties = d
        return answer

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
