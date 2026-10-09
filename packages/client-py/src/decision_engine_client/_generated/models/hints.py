from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.hints_sensitivity_type_0 import HintsSensitivityType0, check_hints_sensitivity_type_0
from ..types import UNSET, Unset

T = TypeVar("T", bound="Hints")


@_attrs_define
class Hints:
    """
    Attributes:
        body (None | str | Unset):
        language (None | str | Unset):
        niche (None | str | Unset):
        sender (None | str | Unset):
        sensitivity (HintsSensitivityType0 | None | Unset):
        title (None | str | Unset):
        url (None | str | Unset):
    """

    body: None | str | Unset = UNSET
    language: None | str | Unset = UNSET
    niche: None | str | Unset = UNSET
    sender: None | str | Unset = UNSET
    sensitivity: HintsSensitivityType0 | None | Unset = UNSET
    title: None | str | Unset = UNSET
    url: None | str | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        body: None | str | Unset
        if isinstance(self.body, Unset):
            body = UNSET
        else:
            body = self.body

        language: None | str | Unset
        if isinstance(self.language, Unset):
            language = UNSET
        else:
            language = self.language

        niche: None | str | Unset
        if isinstance(self.niche, Unset):
            niche = UNSET
        else:
            niche = self.niche

        sender: None | str | Unset
        if isinstance(self.sender, Unset):
            sender = UNSET
        else:
            sender = self.sender

        sensitivity: None | str | Unset
        if isinstance(self.sensitivity, Unset):
            sensitivity = UNSET
        elif isinstance(self.sensitivity, str):
            sensitivity = self.sensitivity
        else:
            sensitivity = self.sensitivity

        title: None | str | Unset
        if isinstance(self.title, Unset):
            title = UNSET
        else:
            title = self.title

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        field_dict: dict[str, Any] = {}

        field_dict.update({})
        if body is not UNSET:
            field_dict["body"] = body
        if language is not UNSET:
            field_dict["language"] = language
        if niche is not UNSET:
            field_dict["niche"] = niche
        if sender is not UNSET:
            field_dict["sender"] = sender
        if sensitivity is not UNSET:
            field_dict["sensitivity"] = sensitivity
        if title is not UNSET:
            field_dict["title"] = title
        if url is not UNSET:
            field_dict["url"] = url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)

        def _parse_body(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        body = _parse_body(d.pop("body", UNSET))

        def _parse_language(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        language = _parse_language(d.pop("language", UNSET))

        def _parse_niche(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        niche = _parse_niche(d.pop("niche", UNSET))

        def _parse_sender(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sender = _parse_sender(d.pop("sender", UNSET))

        def _parse_sensitivity(data: object) -> HintsSensitivityType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                sensitivity_type_0 = check_hints_sensitivity_type_0(data)

                return sensitivity_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(HintsSensitivityType0 | None | Unset, data)

        sensitivity = _parse_sensitivity(d.pop("sensitivity", UNSET))

        def _parse_title(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        title = _parse_title(d.pop("title", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        hints = cls(
            body=body,
            language=language,
            niche=niche,
            sender=sender,
            sensitivity=sensitivity,
            title=title,
            url=url,
        )

        return hints
