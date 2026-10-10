from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.verdict import Verdict, check_verdict
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.decision_in_edits_type_0 import DecisionInEditsType0


T = TypeVar("T", bound="DecisionIn")


@_attrs_define
class DecisionIn:
    """Body of ``POST /v1/items/{id}/decision`` (API.md).

    The "snooze_until is in the future" rule is an API-layer check (``api/v1/decisions.py``): the
    graph re-validates this model on a resume replay, long after the time may have passed.

        Attributes:
            verdict (Verdict):
            edits (DecisionInEditsType0 | None | Unset):
            note (None | str | Unset):
            option (None | str | Unset):
            snooze_until (datetime.datetime | None | Unset):
    """

    verdict: Verdict
    edits: DecisionInEditsType0 | None | Unset = UNSET
    note: None | str | Unset = UNSET
    option: None | str | Unset = UNSET
    snooze_until: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.decision_in_edits_type_0 import DecisionInEditsType0  # noqa: PLC0415

        verdict: str = self.verdict

        edits: dict[str, Any] | None | Unset
        if isinstance(self.edits, Unset):
            edits = UNSET
        elif isinstance(self.edits, DecisionInEditsType0):
            edits = self.edits.to_dict()
        else:
            edits = self.edits

        note: None | str | Unset
        if isinstance(self.note, Unset):
            note = UNSET
        else:
            note = self.note

        option: None | str | Unset
        if isinstance(self.option, Unset):
            option = UNSET
        else:
            option = self.option

        snooze_until: None | str | Unset
        if isinstance(self.snooze_until, Unset):
            snooze_until = UNSET
        elif isinstance(self.snooze_until, datetime.datetime):
            snooze_until = self.snooze_until.isoformat()
        else:
            snooze_until = self.snooze_until

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "verdict": verdict,
            }
        )
        if edits is not UNSET:
            field_dict["edits"] = edits
        if note is not UNSET:
            field_dict["note"] = note
        if option is not UNSET:
            field_dict["option"] = option
        if snooze_until is not UNSET:
            field_dict["snooze_until"] = snooze_until

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.decision_in_edits_type_0 import DecisionInEditsType0  # noqa: PLC0415

        d = dict(src_dict)
        verdict = check_verdict(d.pop("verdict"))

        def _parse_edits(data: object) -> DecisionInEditsType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                edits_type_0 = DecisionInEditsType0.from_dict(data)

                return edits_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecisionInEditsType0 | None | Unset, data)

        edits = _parse_edits(d.pop("edits", UNSET))

        def _parse_note(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        note = _parse_note(d.pop("note", UNSET))

        def _parse_option(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        option = _parse_option(d.pop("option", UNSET))

        def _parse_snooze_until(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                snooze_until_type_0 = datetime.datetime.fromisoformat(data)

                return snooze_until_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        snooze_until = _parse_snooze_until(d.pop("snooze_until", UNSET))

        decision_in = cls(
            verdict=verdict,
            edits=edits,
            note=note,
            option=option,
            snooze_until=snooze_until,
        )

        decision_in.additional_properties = d
        return decision_in

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
