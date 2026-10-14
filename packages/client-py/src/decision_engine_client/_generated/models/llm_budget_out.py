from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="LlmBudgetOut")


@_attrs_define
class LlmBudgetOut:
    """
    Attributes:
        provider (str):
        requests_limit (int | None):
        requests_used (int):
        tokens_limit (int | None):
        tokens_used (int):
    """

    provider: str
    requests_limit: int | None
    requests_used: int
    tokens_limit: int | None
    tokens_used: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        provider = self.provider

        requests_limit: int | None
        requests_limit = self.requests_limit

        requests_used = self.requests_used

        tokens_limit: int | None
        tokens_limit = self.tokens_limit

        tokens_used = self.tokens_used

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "provider": provider,
                "requests_limit": requests_limit,
                "requests_used": requests_used,
                "tokens_limit": tokens_limit,
                "tokens_used": tokens_used,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        provider = d.pop("provider")

        def _parse_requests_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        requests_limit = _parse_requests_limit(d.pop("requests_limit"))

        requests_used = d.pop("requests_used")

        def _parse_tokens_limit(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        tokens_limit = _parse_tokens_limit(d.pop("tokens_limit"))

        tokens_used = d.pop("tokens_used")

        llm_budget_out = cls(
            provider=provider,
            requests_limit=requests_limit,
            requests_used=requests_used,
            tokens_limit=tokens_limit,
            tokens_used=tokens_used,
        )

        llm_budget_out.additional_properties = d
        return llm_budget_out

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
