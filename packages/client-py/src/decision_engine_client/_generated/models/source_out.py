from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SourceOut")


@_attrs_define
class SourceOut:
    """
    Attributes:
        enabled (bool):
        error_count (int):
        id (UUID):
        items_today (int):
        last_polled_at (datetime.datetime | None):
        name (str):
        niche_hint (None | str):
        slug (str):
        type_ (str):
    """

    enabled: bool
    error_count: int
    id: UUID
    items_today: int
    last_polled_at: datetime.datetime | None
    name: str
    niche_hint: None | str
    slug: str
    type_: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        enabled = self.enabled

        error_count = self.error_count

        id = str(self.id)

        items_today = self.items_today

        last_polled_at: None | str
        if isinstance(self.last_polled_at, datetime.datetime):
            last_polled_at = self.last_polled_at.isoformat()
        else:
            last_polled_at = self.last_polled_at

        name = self.name

        niche_hint: None | str
        niche_hint = self.niche_hint

        slug = self.slug

        type_ = self.type_

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "enabled": enabled,
                "error_count": error_count,
                "id": id,
                "items_today": items_today,
                "last_polled_at": last_polled_at,
                "name": name,
                "niche_hint": niche_hint,
                "slug": slug,
                "type": type_,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        enabled = d.pop("enabled")

        error_count = d.pop("error_count")

        id = UUID(d.pop("id"))

        items_today = d.pop("items_today")

        def _parse_last_polled_at(data: object) -> datetime.datetime | None:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                last_polled_at_type_0 = datetime.datetime.fromisoformat(data)

                return last_polled_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None, data)

        last_polled_at = _parse_last_polled_at(d.pop("last_polled_at"))

        name = d.pop("name")

        def _parse_niche_hint(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        niche_hint = _parse_niche_hint(d.pop("niche_hint"))

        slug = d.pop("slug")

        type_ = d.pop("type")

        source_out = cls(
            enabled=enabled,
            error_count=error_count,
            id=id,
            items_today=items_today,
            last_polled_at=last_polled_at,
            name=name,
            niche_hint=niche_hint,
            slug=slug,
            type_=type_,
        )

        source_out.additional_properties = d
        return source_out

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
