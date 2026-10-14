from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ActivityEntry")


@_attrs_define
class ActivityEntry:
    """One executed action on an item. Params and results are not shown: they can hold URLs.

    Attributes:
        action (str):
        created_at (datetime.datetime):
        reversible (bool):
        status (str):
        undone_at (datetime.datetime | None | Unset):
    """

    action: str
    created_at: datetime.datetime
    reversible: bool
    status: str
    undone_at: datetime.datetime | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        action = self.action

        created_at = self.created_at.isoformat()

        reversible = self.reversible

        status = self.status

        undone_at: None | str | Unset
        if isinstance(self.undone_at, Unset):
            undone_at = UNSET
        elif isinstance(self.undone_at, datetime.datetime):
            undone_at = self.undone_at.isoformat()
        else:
            undone_at = self.undone_at

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "action": action,
                "created_at": created_at,
                "reversible": reversible,
                "status": status,
            }
        )
        if undone_at is not UNSET:
            field_dict["undone_at"] = undone_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        action = d.pop("action")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        reversible = d.pop("reversible")

        status = d.pop("status")

        def _parse_undone_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                undone_at_type_0 = datetime.datetime.fromisoformat(data)

                return undone_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        undone_at = _parse_undone_at(d.pop("undone_at", UNSET))

        activity_entry = cls(
            action=action,
            created_at=created_at,
            reversible=reversible,
            status=status,
            undone_at=undone_at,
        )

        activity_entry.additional_properties = d
        return activity_entry

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
