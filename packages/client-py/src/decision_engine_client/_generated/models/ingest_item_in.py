from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.hints import Hints
    from ..models.ingest_item_in_payload_type_0 import IngestItemInPayloadType0


T = TypeVar("T", bound="IngestItemIn")


@_attrs_define
class IngestItemIn:
    """
    Attributes:
        payload (IngestItemInPayloadType0 | list[Any] | str):
        source (str):
        source_ref (str):
        callback_url (None | str | Unset):
        hints (Hints | None | Unset):
        received_at (datetime.datetime | None | Unset):
    """

    payload: IngestItemInPayloadType0 | list[Any] | str
    source: str
    source_ref: str
    callback_url: None | str | Unset = UNSET
    hints: Hints | None | Unset = UNSET
    received_at: datetime.datetime | None | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        from ..models.hints import Hints  # noqa: PLC0415
        from ..models.ingest_item_in_payload_type_0 import IngestItemInPayloadType0  # noqa: PLC0415

        payload: dict[str, Any] | list[Any] | str
        if isinstance(self.payload, IngestItemInPayloadType0):
            payload = self.payload.to_dict()
        elif isinstance(self.payload, list):
            payload = self.payload

        else:
            payload = self.payload

        source = self.source

        source_ref = self.source_ref

        callback_url: None | str | Unset
        if isinstance(self.callback_url, Unset):
            callback_url = UNSET
        else:
            callback_url = self.callback_url

        hints: dict[str, Any] | None | Unset
        if isinstance(self.hints, Unset):
            hints = UNSET
        elif isinstance(self.hints, Hints):
            hints = self.hints.to_dict()
        else:
            hints = self.hints

        received_at: None | str | Unset
        if isinstance(self.received_at, Unset):
            received_at = UNSET
        elif isinstance(self.received_at, datetime.datetime):
            received_at = self.received_at.isoformat()
        else:
            received_at = self.received_at

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "payload": payload,
                "source": source,
                "source_ref": source_ref,
            }
        )
        if callback_url is not UNSET:
            field_dict["callback_url"] = callback_url
        if hints is not UNSET:
            field_dict["hints"] = hints
        if received_at is not UNSET:
            field_dict["received_at"] = received_at

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.hints import Hints  # noqa: PLC0415
        from ..models.ingest_item_in_payload_type_0 import IngestItemInPayloadType0  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_payload(data: object) -> IngestItemInPayloadType0 | list[Any] | str:
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                payload_type_0 = IngestItemInPayloadType0.from_dict(data)

                return payload_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                if not isinstance(data, list):
                    raise TypeError()
                payload_type_1 = cast(list[Any], data)

                return payload_type_1
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(IngestItemInPayloadType0 | list[Any] | str, data)

        payload = _parse_payload(d.pop("payload"))

        source = d.pop("source")

        source_ref = d.pop("source_ref")

        def _parse_callback_url(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        callback_url = _parse_callback_url(d.pop("callback_url", UNSET))

        def _parse_hints(data: object) -> Hints | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                hints_type_0 = Hints.from_dict(data)

                return hints_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(Hints | None | Unset, data)

        hints = _parse_hints(d.pop("hints", UNSET))

        def _parse_received_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                received_at_type_0 = datetime.datetime.fromisoformat(data)

                return received_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        received_at = _parse_received_at(d.pop("received_at", UNSET))

        ingest_item_in = cls(
            payload=payload,
            source=source,
            source_ref=source_ref,
            callback_url=callback_url,
            hints=hints,
            received_at=received_at,
        )

        return ingest_item_in
