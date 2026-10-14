from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.niche_row_autonomy import NicheRowAutonomy, check_niche_row_autonomy
from ..models.niche_row_laya_mode import NicheRowLayaMode, check_niche_row_laya_mode
from ..models.niche_row_source import NicheRowSource, check_niche_row_source

T = TypeVar("T", bound="NicheRow")


@_attrs_define
class NicheRow:
    """
    Attributes:
        auto_actions (list[str]):
        autonomy (NicheRowAutonomy):
        description (str):
        enabled (bool):
        label (str):
        laya_mode (NicheRowLayaMode):
        name (str):
        source (NicheRowSource):
        version (int):
    """

    auto_actions: list[str]
    autonomy: NicheRowAutonomy
    description: str
    enabled: bool
    label: str
    laya_mode: NicheRowLayaMode
    name: str
    source: NicheRowSource
    version: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        auto_actions = self.auto_actions

        autonomy: str = self.autonomy

        description = self.description

        enabled = self.enabled

        label = self.label

        laya_mode: str = self.laya_mode

        name = self.name

        source: str = self.source

        version = self.version

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "auto_actions": auto_actions,
                "autonomy": autonomy,
                "description": description,
                "enabled": enabled,
                "label": label,
                "laya_mode": laya_mode,
                "name": name,
                "source": source,
                "version": version,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        auto_actions = cast(list[str], d.pop("auto_actions"))

        autonomy = check_niche_row_autonomy(d.pop("autonomy"))

        description = d.pop("description")

        enabled = d.pop("enabled")

        label = d.pop("label")

        laya_mode = check_niche_row_laya_mode(d.pop("laya_mode"))

        name = d.pop("name")

        source = check_niche_row_source(d.pop("source"))

        version = d.pop("version")

        niche_row = cls(
            auto_actions=auto_actions,
            autonomy=autonomy,
            description=description,
            enabled=enabled,
            label=label,
            laya_mode=laya_mode,
            name=name,
            source=source,
            version=version,
        )

        niche_row.additional_properties = d
        return niche_row

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
