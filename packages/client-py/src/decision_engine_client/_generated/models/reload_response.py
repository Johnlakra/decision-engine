from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.reload_response_errors_item import ReloadResponseErrorsItem


T = TypeVar("T", bound="ReloadResponse")


@_attrs_define
class ReloadResponse:
    """
    Attributes:
        loaded (list[str]):
        errors (list[ReloadResponseErrorsItem] | Unset):
    """

    loaded: list[str]
    errors: list[ReloadResponseErrorsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        loaded = self.loaded

        errors: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.errors, Unset):
            errors = []
            for errors_item_data in self.errors:
                errors_item = errors_item_data.to_dict()
                errors.append(errors_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "loaded": loaded,
            }
        )
        if errors is not UNSET:
            field_dict["errors"] = errors

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.reload_response_errors_item import ReloadResponseErrorsItem  # noqa: PLC0415

        d = dict(src_dict)
        loaded = cast(list[str], d.pop("loaded"))

        _errors = d.pop("errors", UNSET)
        errors: list[ReloadResponseErrorsItem] | Unset = UNSET
        if _errors is not UNSET:
            errors = []
            for errors_item_data in _errors:
                errors_item = ReloadResponseErrorsItem.from_dict(errors_item_data)

                errors.append(errors_item)

        reload_response = cls(
            loaded=loaded,
            errors=errors,
        )

        reload_response.additional_properties = d
        return reload_response

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
