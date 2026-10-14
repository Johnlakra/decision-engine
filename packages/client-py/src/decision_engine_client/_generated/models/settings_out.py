from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.settings_out_languages_item import SettingsOutLanguagesItem, check_settings_out_languages_item
from ..models.settings_out_laya_mode_default import SettingsOutLayaModeDefault, check_settings_out_laya_mode_default
from ..models.settings_out_laya_mode_type_0 import SettingsOutLayaModeType0, check_settings_out_laya_mode_type_0

if TYPE_CHECKING:
    from ..models.settings_out_laya_mode_by_niche import SettingsOutLayaModeByNiche


T = TypeVar("T", bound="SettingsOut")


@_attrs_define
class SettingsOut:
    """
    Attributes:
        digest_hour (int):
        interests (list[str]):
        languages (list[SettingsOutLanguagesItem]):
        laya_mode (None | SettingsOutLayaModeType0): Stored tenant mode; null = the env default applies
        laya_mode_by_niche (SettingsOutLayaModeByNiche): Stored per-niche overrides
        laya_mode_default (SettingsOutLayaModeDefault): Read-only env LAYA_MODE
        ping_cap_per_day (int):
        quiet_hours (list[int]):
    """

    digest_hour: int
    interests: list[str]
    languages: list[SettingsOutLanguagesItem]
    laya_mode: None | SettingsOutLayaModeType0
    laya_mode_by_niche: SettingsOutLayaModeByNiche
    laya_mode_default: SettingsOutLayaModeDefault
    ping_cap_per_day: int
    quiet_hours: list[int]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        digest_hour = self.digest_hour

        interests = self.interests

        languages = []
        for languages_item_data in self.languages:
            languages_item: str = languages_item_data
            languages.append(languages_item)

        laya_mode: None | str
        if isinstance(self.laya_mode, str):
            laya_mode = self.laya_mode
        else:
            laya_mode = self.laya_mode

        laya_mode_by_niche = self.laya_mode_by_niche.to_dict()

        laya_mode_default: str = self.laya_mode_default

        ping_cap_per_day = self.ping_cap_per_day

        quiet_hours = self.quiet_hours

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "digest_hour": digest_hour,
                "interests": interests,
                "languages": languages,
                "laya_mode": laya_mode,
                "laya_mode_by_niche": laya_mode_by_niche,
                "laya_mode_default": laya_mode_default,
                "ping_cap_per_day": ping_cap_per_day,
                "quiet_hours": quiet_hours,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.settings_out_laya_mode_by_niche import SettingsOutLayaModeByNiche  # noqa: PLC0415

        d = dict(src_dict)
        digest_hour = d.pop("digest_hour")

        interests = cast(list[str], d.pop("interests"))

        languages = []
        _languages = d.pop("languages")
        for languages_item_data in _languages:
            languages_item = check_settings_out_languages_item(languages_item_data)

            languages.append(languages_item)

        def _parse_laya_mode(data: object) -> None | SettingsOutLayaModeType0:
            if data is None:
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                laya_mode_type_0 = check_settings_out_laya_mode_type_0(data)

                return laya_mode_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SettingsOutLayaModeType0, data)

        laya_mode = _parse_laya_mode(d.pop("laya_mode"))

        laya_mode_by_niche = SettingsOutLayaModeByNiche.from_dict(d.pop("laya_mode_by_niche"))

        laya_mode_default = check_settings_out_laya_mode_default(d.pop("laya_mode_default"))

        ping_cap_per_day = d.pop("ping_cap_per_day")

        quiet_hours = cast(list[int], d.pop("quiet_hours"))

        settings_out = cls(
            digest_hour=digest_hour,
            interests=interests,
            languages=languages,
            laya_mode=laya_mode,
            laya_mode_by_niche=laya_mode_by_niche,
            laya_mode_default=laya_mode_default,
            ping_cap_per_day=ping_cap_per_day,
            quiet_hours=quiet_hours,
        )

        settings_out.additional_properties = d
        return settings_out

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
