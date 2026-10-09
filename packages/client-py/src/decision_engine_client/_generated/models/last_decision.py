from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="LastDecision")


@_attrs_define
class LastDecision:
    """
    Attributes:
        decided_at (datetime.datetime):
        decided_by (str):
        verdict (str):
        option (None | str | Unset):
    """

    decided_at: datetime.datetime
    decided_by: str
    verdict: str
    option: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        decided_at = self.decided_at.isoformat()

        decided_by = self.decided_by

        verdict = self.verdict

        option: None | str | Unset
        if isinstance(self.option, Unset):
            option = UNSET
        else:
            option = self.option

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "decided_at": decided_at,
                "decided_by": decided_by,
                "verdict": verdict,
            }
        )
        if option is not UNSET:
            field_dict["option"] = option

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        decided_at = datetime.datetime.fromisoformat(d.pop("decided_at"))

        decided_by = d.pop("decided_by")

        verdict = d.pop("verdict")

        def _parse_option(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        option = _parse_option(d.pop("option", UNSET))

        last_decision = cls(
            decided_at=decided_at,
            decided_by=decided_by,
            verdict=verdict,
            option=option,
        )

        last_decision.additional_properties = d
        return last_decision

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
