from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.normalised_content_attachments_item import NormalisedContentAttachmentsItem
    from ..models.normalised_content_entities import NormalisedContentEntities


T = TypeVar("T", bound="NormalisedContent")


@_attrs_define
class NormalisedContent:
    """
    Attributes:
        title (str):
        attachments (list[NormalisedContentAttachmentsItem] | Unset):
        body (str | Unset):  Default: ''.
        entities (NormalisedContentEntities | Unset):
        flags (list[str] | Unset):
        language (None | str | Unset):
        sender (None | str | Unset):
        summary (None | str | Unset):
        url (None | str | Unset):
    """

    title: str
    attachments: list[NormalisedContentAttachmentsItem] | Unset = UNSET
    body: str | Unset = ""
    entities: NormalisedContentEntities | Unset = UNSET
    flags: list[str] | Unset = UNSET
    language: None | str | Unset = UNSET
    sender: None | str | Unset = UNSET
    summary: None | str | Unset = UNSET
    url: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        title = self.title

        attachments: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.attachments, Unset):
            attachments = []
            for attachments_item_data in self.attachments:
                attachments_item = attachments_item_data.to_dict()
                attachments.append(attachments_item)

        body = self.body

        entities: dict[str, Any] | Unset = UNSET
        if not isinstance(self.entities, Unset):
            entities = self.entities.to_dict()

        flags: list[str] | Unset = UNSET
        if not isinstance(self.flags, Unset):
            flags = self.flags

        language: None | str | Unset
        if isinstance(self.language, Unset):
            language = UNSET
        else:
            language = self.language

        sender: None | str | Unset
        if isinstance(self.sender, Unset):
            sender = UNSET
        else:
            sender = self.sender

        summary: None | str | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        else:
            summary = self.summary

        url: None | str | Unset
        if isinstance(self.url, Unset):
            url = UNSET
        else:
            url = self.url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "title": title,
            }
        )
        if attachments is not UNSET:
            field_dict["attachments"] = attachments
        if body is not UNSET:
            field_dict["body"] = body
        if entities is not UNSET:
            field_dict["entities"] = entities
        if flags is not UNSET:
            field_dict["flags"] = flags
        if language is not UNSET:
            field_dict["language"] = language
        if sender is not UNSET:
            field_dict["sender"] = sender
        if summary is not UNSET:
            field_dict["summary"] = summary
        if url is not UNSET:
            field_dict["url"] = url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.normalised_content_attachments_item import NormalisedContentAttachmentsItem  # noqa: PLC0415
        from ..models.normalised_content_entities import NormalisedContentEntities  # noqa: PLC0415

        d = dict(src_dict)
        title = d.pop("title")

        _attachments = d.pop("attachments", UNSET)
        attachments: list[NormalisedContentAttachmentsItem] | Unset = UNSET
        if _attachments is not UNSET:
            attachments = []
            for attachments_item_data in _attachments:
                attachments_item = NormalisedContentAttachmentsItem.from_dict(attachments_item_data)

                attachments.append(attachments_item)

        body = d.pop("body", UNSET)

        _entities = d.pop("entities", UNSET)
        entities: NormalisedContentEntities | Unset
        if isinstance(_entities, Unset):
            entities = UNSET
        else:
            entities = NormalisedContentEntities.from_dict(_entities)

        flags = cast(list[str], d.pop("flags", UNSET))

        def _parse_language(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        language = _parse_language(d.pop("language", UNSET))

        def _parse_sender(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        sender = _parse_sender(d.pop("sender", UNSET))

        def _parse_summary(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        def _parse_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        url = _parse_url(d.pop("url", UNSET))

        normalised_content = cls(
            title=title,
            attachments=attachments,
            body=body,
            entities=entities,
            flags=flags,
            language=language,
            sender=sender,
            summary=summary,
            url=url,
        )

        normalised_content.additional_properties = d
        return normalised_content

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
