from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.niche_detail_source import NicheDetailSource, check_niche_detail_source

if TYPE_CHECKING:
    from ..models.niche_detail_config import NicheDetailConfig


T = TypeVar("T", bound="NicheDetail")


@_attrs_define
class NicheDetail:
    """
    Attributes:
        config (NicheDetailConfig):
        name (str):
        source (NicheDetailSource):
        version (int):
        yaml (str):
    """

    config: NicheDetailConfig
    name: str
    source: NicheDetailSource
    version: int
    yaml: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        config = self.config.to_dict()

        name = self.name

        source: str = self.source

        version = self.version

        yaml = self.yaml

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "config": config,
                "name": name,
                "source": source,
                "version": version,
                "yaml": yaml,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.niche_detail_config import NicheDetailConfig  # noqa: PLC0415

        d = dict(src_dict)
        config = NicheDetailConfig.from_dict(d.pop("config"))

        name = d.pop("name")

        source = check_niche_detail_source(d.pop("source"))

        version = d.pop("version")

        yaml = d.pop("yaml")

        niche_detail = cls(
            config=config,
            name=name,
            source=source,
            version=version,
            yaml=yaml,
        )

        niche_detail.additional_properties = d
        return niche_detail

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
