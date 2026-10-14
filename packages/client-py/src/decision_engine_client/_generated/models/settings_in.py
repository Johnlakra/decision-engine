from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.settings_in_languages_item import SettingsInLanguagesItem, check_settings_in_languages_item

T = TypeVar("T", bound="SettingsIn")


@_attrs_define
class SettingsIn:
    """Full replacement of the editable settings. Unknown keys are refused.

    Attributes:
        digest_hour (int):
        interests (list[str]):
        languages (list[SettingsInLanguagesItem]):
        ping_cap_per_day (int):
        quiet_hours (list[int]):
    """

    digest_hour: int
    interests: list[str]
    languages: list[SettingsInLanguagesItem]
    ping_cap_per_day: int
    quiet_hours: list[int]

    def to_dict(self) -> dict[str, Any]:
        digest_hour = self.digest_hour

        interests = self.interests

        languages = []
        for languages_item_data in self.languages:
            languages_item: str = languages_item_data
            languages.append(languages_item)

        ping_cap_per_day = self.ping_cap_per_day

        quiet_hours = self.quiet_hours

        field_dict: dict[str, Any] = {}

        field_dict.update(
            {
                "digest_hour": digest_hour,
                "interests": interests,
                "languages": languages,
                "ping_cap_per_day": ping_cap_per_day,
                "quiet_hours": quiet_hours,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        digest_hour = d.pop("digest_hour")

        interests = cast(list[str], d.pop("interests"))

        languages = []
        _languages = d.pop("languages")
        for languages_item_data in _languages:
            languages_item = check_settings_in_languages_item(languages_item_data)

            languages.append(languages_item)

        ping_cap_per_day = d.pop("ping_cap_per_day")

        quiet_hours = cast(list[int], d.pop("quiet_hours"))

        settings_in = cls(
            digest_hour=digest_hour,
            interests=interests,
            languages=languages,
            ping_cap_per_day=ping_cap_per_day,
            quiet_hours=quiet_hours,
        )

        return settings_in
