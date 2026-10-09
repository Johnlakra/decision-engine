from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.deep_health_status import DeepHealthStatus, check_deep_health_status
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.deep_health_llm import DeepHealthLlm
    from ..models.deep_health_niches import DeepHealthNiches


T = TypeVar("T", bound="DeepHealth")


@_attrs_define
class DeepHealth:
    """
    Attributes:
        db (str):
        laya (str):
        llm (DeepHealthLlm):
        niches (DeepHealthNiches):
        oldest_job_age_s (float | None):
        queue_depth (int | None):
        redis (str):
        status (DeepHealthStatus):
        db_pooler (bool | Unset):  Default: False.
    """

    db: str
    laya: str
    llm: DeepHealthLlm
    niches: DeepHealthNiches
    oldest_job_age_s: float | None
    queue_depth: int | None
    redis: str
    status: DeepHealthStatus
    db_pooler: bool | Unset = False
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        db = self.db

        laya = self.laya

        llm = self.llm.to_dict()

        niches = self.niches.to_dict()

        oldest_job_age_s: float | None
        oldest_job_age_s = self.oldest_job_age_s

        queue_depth: int | None
        queue_depth = self.queue_depth

        redis = self.redis

        status: str = self.status

        db_pooler = self.db_pooler

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "db": db,
                "laya": laya,
                "llm": llm,
                "niches": niches,
                "oldest_job_age_s": oldest_job_age_s,
                "queue_depth": queue_depth,
                "redis": redis,
                "status": status,
            }
        )
        if db_pooler is not UNSET:
            field_dict["db_pooler"] = db_pooler

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.deep_health_llm import DeepHealthLlm  # noqa: PLC0415
        from ..models.deep_health_niches import DeepHealthNiches  # noqa: PLC0415

        d = dict(src_dict)
        db = d.pop("db")

        laya = d.pop("laya")

        llm = DeepHealthLlm.from_dict(d.pop("llm"))

        niches = DeepHealthNiches.from_dict(d.pop("niches"))

        def _parse_oldest_job_age_s(data: object) -> float | None:
            if data is None:
                return data
            return cast(float | None, data)

        oldest_job_age_s = _parse_oldest_job_age_s(d.pop("oldest_job_age_s"))

        def _parse_queue_depth(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        queue_depth = _parse_queue_depth(d.pop("queue_depth"))

        redis = d.pop("redis")

        status = check_deep_health_status(d.pop("status"))

        db_pooler = d.pop("db_pooler", UNSET)

        deep_health = cls(
            db=db,
            laya=laya,
            llm=llm,
            niches=niches,
            oldest_job_age_s=oldest_job_age_s,
            queue_depth=queue_depth,
            redis=redis,
            status=status,
            db_pooler=db_pooler,
        )

        deep_health.additional_properties = d
        return deep_health

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
