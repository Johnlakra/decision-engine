from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.llm_budget_out import LlmBudgetOut
    from ..models.stats_today_by_niche import StatsTodayByNiche
    from ..models.stats_today_by_status import StatsTodayByStatus


T = TypeVar("T", bound="StatsToday")


@_attrs_define
class StatsToday:
    """
    Attributes:
        auto_handled (int):
        by_niche (StatsTodayByNiche):
        by_status (StatsTodayByStatus):
        date (str):
        decided (int):
        discarded (int):
        items_in (int):
        laya_agreement (float | None):
        laya_mode (str):
        llm (list[LlmBudgetOut]):
    """

    auto_handled: int
    by_niche: StatsTodayByNiche
    by_status: StatsTodayByStatus
    date: str
    decided: int
    discarded: int
    items_in: int
    laya_agreement: float | None
    laya_mode: str
    llm: list[LlmBudgetOut]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        auto_handled = self.auto_handled

        by_niche = self.by_niche.to_dict()

        by_status = self.by_status.to_dict()

        date = self.date

        decided = self.decided

        discarded = self.discarded

        items_in = self.items_in

        laya_agreement: float | None
        laya_agreement = self.laya_agreement

        laya_mode = self.laya_mode

        llm = []
        for llm_item_data in self.llm:
            llm_item = llm_item_data.to_dict()
            llm.append(llm_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "auto_handled": auto_handled,
                "by_niche": by_niche,
                "by_status": by_status,
                "date": date,
                "decided": decided,
                "discarded": discarded,
                "items_in": items_in,
                "laya_agreement": laya_agreement,
                "laya_mode": laya_mode,
                "llm": llm,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.llm_budget_out import LlmBudgetOut  # noqa: PLC0415
        from ..models.stats_today_by_niche import StatsTodayByNiche  # noqa: PLC0415
        from ..models.stats_today_by_status import StatsTodayByStatus  # noqa: PLC0415

        d = dict(src_dict)
        auto_handled = d.pop("auto_handled")

        by_niche = StatsTodayByNiche.from_dict(d.pop("by_niche"))

        by_status = StatsTodayByStatus.from_dict(d.pop("by_status"))

        date = d.pop("date")

        decided = d.pop("decided")

        discarded = d.pop("discarded")

        items_in = d.pop("items_in")

        def _parse_laya_agreement(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        laya_agreement = _parse_laya_agreement(d.pop("laya_agreement"))

        laya_mode = d.pop("laya_mode")

        llm = []
        _llm = d.pop("llm")
        for llm_item_data in _llm:
            llm_item = LlmBudgetOut.from_dict(llm_item_data)

            llm.append(llm_item)

        stats_today = cls(
            auto_handled=auto_handled,
            by_niche=by_niche,
            by_status=by_status,
            date=date,
            decided=decided,
            discarded=discarded,
            items_in=items_in,
            laya_agreement=laya_agreement,
            laya_mode=laya_mode,
            llm=llm,
        )

        stats_today.additional_properties = d
        return stats_today

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
