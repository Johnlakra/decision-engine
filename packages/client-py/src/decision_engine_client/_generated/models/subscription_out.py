from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SubscriptionOut")


@_attrs_define
class SubscriptionOut:
    """
    Attributes:
        created_at (datetime.datetime):
        enabled (bool):
        events (list[str]):
        id (UUID):
        url (str):
    """

    created_at: datetime.datetime
    enabled: bool
    events: list[str]
    id: UUID
    url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at.isoformat()

        enabled = self.enabled

        events = self.events

        id = str(self.id)

        url = self.url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created_at": created_at,
                "enabled": enabled,
                "events": events,
                "id": id,
                "url": url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        enabled = d.pop("enabled")

        events = cast(list[str], d.pop("events"))

        id = UUID(d.pop("id"))

        url = d.pop("url")

        subscription_out = cls(
            created_at=created_at,
            enabled=enabled,
            events=events,
            id=id,
            url=url,
        )

        subscription_out.additional_properties = d
        return subscription_out

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
