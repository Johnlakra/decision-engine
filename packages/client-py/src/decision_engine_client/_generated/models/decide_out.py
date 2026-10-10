from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.decide_out_answers import DecideOutAnswers
    from ..models.decide_out_decision_type_0 import DecideOutDecisionType0
    from ..models.shadow_record import ShadowRecord


T = TypeVar("T", bound="DecideOut")


@_attrs_define
class DecideOut:
    """
    Attributes:
        answers (DecideOutAnswers):
        fallback (bool):
        decision (DecideOutDecisionType0 | None | Unset):
        explanation (None | str | Unset):
        model (None | str | Unset):
        shadow (None | ShadowRecord | Unset):
    """

    answers: DecideOutAnswers
    fallback: bool
    decision: DecideOutDecisionType0 | None | Unset = UNSET
    explanation: None | str | Unset = UNSET
    model: None | str | Unset = UNSET
    shadow: None | ShadowRecord | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.decide_out_decision_type_0 import DecideOutDecisionType0  # noqa: PLC0415
        from ..models.shadow_record import ShadowRecord  # noqa: PLC0415

        answers = self.answers.to_dict()

        fallback = self.fallback

        decision: dict[str, Any] | None | Unset
        if isinstance(self.decision, Unset):
            decision = UNSET
        elif isinstance(self.decision, DecideOutDecisionType0):
            decision = self.decision.to_dict()
        else:
            decision = self.decision

        explanation: None | str | Unset
        if isinstance(self.explanation, Unset):
            explanation = UNSET
        else:
            explanation = self.explanation

        model: None | str | Unset
        if isinstance(self.model, Unset):
            model = UNSET
        else:
            model = self.model

        shadow: dict[str, Any] | None | Unset
        if isinstance(self.shadow, Unset):
            shadow = UNSET
        elif isinstance(self.shadow, ShadowRecord):
            shadow = self.shadow.to_dict()
        else:
            shadow = self.shadow

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "answers": answers,
                "fallback": fallback,
            }
        )
        if decision is not UNSET:
            field_dict["decision"] = decision
        if explanation is not UNSET:
            field_dict["explanation"] = explanation
        if model is not UNSET:
            field_dict["model"] = model
        if shadow is not UNSET:
            field_dict["shadow"] = shadow

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.decide_out_answers import DecideOutAnswers  # noqa: PLC0415
        from ..models.decide_out_decision_type_0 import DecideOutDecisionType0  # noqa: PLC0415
        from ..models.shadow_record import ShadowRecord  # noqa: PLC0415

        d = dict(src_dict)
        answers = DecideOutAnswers.from_dict(d.pop("answers"))

        fallback = d.pop("fallback")

        def _parse_decision(data: object) -> DecideOutDecisionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                decision_type_0 = DecideOutDecisionType0.from_dict(data)

                return decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecideOutDecisionType0 | None | Unset, data)

        decision = _parse_decision(d.pop("decision", UNSET))

        def _parse_explanation(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        explanation = _parse_explanation(d.pop("explanation", UNSET))

        def _parse_model(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        model = _parse_model(d.pop("model", UNSET))

        def _parse_shadow(data: object) -> None | ShadowRecord | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                shadow_type_0 = ShadowRecord.from_dict(data)

                return shadow_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ShadowRecord | Unset, data)

        shadow = _parse_shadow(d.pop("shadow", UNSET))

        decide_out = cls(
            answers=answers,
            fallback=fallback,
            decision=decision,
            explanation=explanation,
            model=model,
            shadow=shadow,
        )

        decide_out.additional_properties = d
        return decide_out

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
