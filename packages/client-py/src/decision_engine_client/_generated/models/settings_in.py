from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define

from ..models.settings_in_languages_item import SettingsInLanguagesItem, check_settings_in_languages_item
from ..models.settings_in_laya_mode_type_0 import SettingsInLayaModeType0, check_settings_in_laya_mode_type_0
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.settings_in_laya_mode_by_niche import SettingsInLayaModeByNiche


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
        laya_mode (None | SettingsInLayaModeType0 | Unset): Absent = unchanged; null = use env LAYA_MODE. Changing to
            'on' is refused.
        laya_mode_by_niche (SettingsInLayaModeByNiche | Unset): Absent = unchanged; otherwise a full replacement ({}
            clears every override).
    """

    digest_hour: int
    interests: list[str]
    languages: list[SettingsInLanguagesItem]
    ping_cap_per_day: int
    quiet_hours: list[int]
    laya_mode: None | SettingsInLayaModeType0 | Unset = UNSET
    laya_mode_by_niche: SettingsInLayaModeByNiche | Unset = UNSET

    def to_dict(self) -> dict[str, Any]:
        digest_hour = self.digest_hour

        interests = self.interests

        languages = []
        for languages_item_data in self.languages:
            languages_item: str = languages_item_data
            languages.append(languages_item)

        ping_cap_per_day = self.ping_cap_per_day

        quiet_hours = self.quiet_hours

        laya_mode: None | str | Unset
        if isinstance(self.laya_mode, Unset):
            laya_mode = UNSET
        elif isinstance(self.laya_mode, str):
            laya_mode = self.laya_mode
        else:
            laya_mode = self.laya_mode

        laya_mode_by_niche: dict[str, Any] | Unset = UNSET
        if not isinstance(self.laya_mode_by_niche, Unset):
            laya_mode_by_niche = self.laya_mode_by_niche.to_dict()

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
        if laya_mode is not UNSET:
            field_dict["laya_mode"] = laya_mode
        if laya_mode_by_niche is not UNSET:
            field_dict["laya_mode_by_niche"] = laya_mode_by_niche

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.settings_in_laya_mode_by_niche import SettingsInLayaModeByNiche  # noqa: PLC0415

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

        def _parse_laya_mode(data: object) -> None | SettingsInLayaModeType0 | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                laya_mode_type_0 = check_settings_in_laya_mode_type_0(data)

                return laya_mode_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SettingsInLayaModeType0 | Unset, data)

        laya_mode = _parse_laya_mode(d.pop("laya_mode", UNSET))

        _laya_mode_by_niche = d.pop("laya_mode_by_niche", UNSET)
        laya_mode_by_niche: SettingsInLayaModeByNiche | Unset
        if isinstance(_laya_mode_by_niche, Unset):
            laya_mode_by_niche = UNSET
        else:
            laya_mode_by_niche = SettingsInLayaModeByNiche.from_dict(_laya_mode_by_niche)

        settings_in = cls(
            digest_hour=digest_hour,
            interests=interests,
            languages=languages,
            ping_cap_per_day=ping_cap_per_day,
            quiet_hours=quiet_hours,
            laya_mode=laya_mode,
            laya_mode_by_niche=laya_mode_by_niche,
        )

        return settings_in
