from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.source_in_config import SourceInConfig


T = TypeVar("T", bound="SourceIn")


@_attrs_define
class SourceIn:
    """
    Attributes:
        config (SourceInConfig): rss: {url}; google_news: {query}
        name (str):
        slug (str):
        type_ (str): Phase 3 accepts rss and google_news only
        niche_hint (None | str | Unset):
    """

    config: SourceInConfig
    name: str
    slug: str
    type_: str
    niche_hint: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        config = self.config.to_dict()

        name = self.name

        slug = self.slug

        type_ = self.type_

        niche_hint: None | str | Unset
        if isinstance(self.niche_hint, Unset):
            niche_hint = UNSET
        else:
            niche_hint = self.niche_hint

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "config": config,
                "name": name,
                "slug": slug,
                "type": type_,
            }
        )
        if niche_hint is not UNSET:
            field_dict["niche_hint"] = niche_hint

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.source_in_config import SourceInConfig  # noqa: PLC0415

        d = dict(src_dict)
        config = SourceInConfig.from_dict(d.pop("config"))

        name = d.pop("name")

        slug = d.pop("slug")

        type_ = d.pop("type")

        def _parse_niche_hint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        niche_hint = _parse_niche_hint(d.pop("niche_hint", UNSET))

        source_in = cls(
            config=config,
            name=name,
            slug=slug,
            type_=type_,
            niche_hint=niche_hint,
        )

        return source_in
