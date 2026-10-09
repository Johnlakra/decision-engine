from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.decision_item_out_decision_type_0 import DecisionItemOutDecisionType0
    from ..models.decision_item_out_triage_type_0 import DecisionItemOutTriageType0
    from ..models.last_decision import LastDecision
    from ..models.normalised_content import NormalisedContent


T = TypeVar("T", bound="DecisionItemOut")


@_attrs_define
class DecisionItemOut:
    """
    Attributes:
        created_at (datetime.datetime):
        id (UUID):
        received_at (datetime.datetime):
        sensitivity (str):
        source (str):
        source_ref (str):
        status (str):
        tenant_id (UUID):
        updated_at (datetime.datetime):
        content (None | NormalisedContent | Unset):
        deadline_at (datetime.datetime | None | Unset):
        decision (DecisionItemOutDecisionType0 | None | Unset):
        language (None | str | Unset):
        last_decision (LastDecision | None | Unset):
        niche (None | str | Unset):
        related_to (None | Unset | UUID):
        risk (None | str | Unset):
        triage (DecisionItemOutTriageType0 | None | Unset):
        urgency (int | None | Unset):
    """

    created_at: datetime.datetime
    id: UUID
    received_at: datetime.datetime
    sensitivity: str
    source: str
    source_ref: str
    status: str
    tenant_id: UUID
    updated_at: datetime.datetime
    content: None | NormalisedContent | Unset = UNSET
    deadline_at: datetime.datetime | None | Unset = UNSET
    decision: DecisionItemOutDecisionType0 | None | Unset = UNSET
    language: None | str | Unset = UNSET
    last_decision: LastDecision | None | Unset = UNSET
    niche: None | str | Unset = UNSET
    related_to: None | Unset | UUID = UNSET
    risk: None | str | Unset = UNSET
    triage: DecisionItemOutTriageType0 | None | Unset = UNSET
    urgency: int | None | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.decision_item_out_decision_type_0 import DecisionItemOutDecisionType0  # noqa: PLC0415
        from ..models.decision_item_out_triage_type_0 import DecisionItemOutTriageType0  # noqa: PLC0415
        from ..models.last_decision import LastDecision  # noqa: PLC0415
        from ..models.normalised_content import NormalisedContent  # noqa: PLC0415

        created_at = self.created_at.isoformat()

        id = str(self.id)

        received_at = self.received_at.isoformat()

        sensitivity = self.sensitivity

        source = self.source

        source_ref = self.source_ref

        status = self.status

        tenant_id = str(self.tenant_id)

        updated_at = self.updated_at.isoformat()

        content: dict[str, Any] | None | Unset
        if isinstance(self.content, Unset):
            content = UNSET
        elif isinstance(self.content, NormalisedContent):
            content = self.content.to_dict()
        else:
            content = self.content

        deadline_at: None | str | Unset
        if isinstance(self.deadline_at, Unset):
            deadline_at = UNSET
        elif isinstance(self.deadline_at, datetime.datetime):
            deadline_at = self.deadline_at.isoformat()
        else:
            deadline_at = self.deadline_at

        decision: dict[str, Any] | None | Unset
        if isinstance(self.decision, Unset):
            decision = UNSET
        elif isinstance(self.decision, DecisionItemOutDecisionType0):
            decision = self.decision.to_dict()
        else:
            decision = self.decision

        language: None | str | Unset
        if isinstance(self.language, Unset):
            language = UNSET
        else:
            language = self.language

        last_decision: dict[str, Any] | None | Unset
        if isinstance(self.last_decision, Unset):
            last_decision = UNSET
        elif isinstance(self.last_decision, LastDecision):
            last_decision = self.last_decision.to_dict()
        else:
            last_decision = self.last_decision

        niche: None | str | Unset
        if isinstance(self.niche, Unset):
            niche = UNSET
        else:
            niche = self.niche

        related_to: None | str | Unset
        if isinstance(self.related_to, Unset):
            related_to = UNSET
        elif isinstance(self.related_to, UUID):
            related_to = str(self.related_to)
        else:
            related_to = self.related_to

        risk: None | str | Unset
        if isinstance(self.risk, Unset):
            risk = UNSET
        else:
            risk = self.risk

        triage: dict[str, Any] | None | Unset
        if isinstance(self.triage, Unset):
            triage = UNSET
        elif isinstance(self.triage, DecisionItemOutTriageType0):
            triage = self.triage.to_dict()
        else:
            triage = self.triage

        urgency: int | None | Unset
        if isinstance(self.urgency, Unset):
            urgency = UNSET
        else:
            urgency = self.urgency

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "created_at": created_at,
                "id": id,
                "received_at": received_at,
                "sensitivity": sensitivity,
                "source": source,
                "source_ref": source_ref,
                "status": status,
                "tenant_id": tenant_id,
                "updated_at": updated_at,
            }
        )
        if content is not UNSET:
            field_dict["content"] = content
        if deadline_at is not UNSET:
            field_dict["deadline_at"] = deadline_at
        if decision is not UNSET:
            field_dict["decision"] = decision
        if language is not UNSET:
            field_dict["language"] = language
        if last_decision is not UNSET:
            field_dict["last_decision"] = last_decision
        if niche is not UNSET:
            field_dict["niche"] = niche
        if related_to is not UNSET:
            field_dict["related_to"] = related_to
        if risk is not UNSET:
            field_dict["risk"] = risk
        if triage is not UNSET:
            field_dict["triage"] = triage
        if urgency is not UNSET:
            field_dict["urgency"] = urgency

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.decision_item_out_decision_type_0 import DecisionItemOutDecisionType0  # noqa: PLC0415
        from ..models.decision_item_out_triage_type_0 import DecisionItemOutTriageType0  # noqa: PLC0415
        from ..models.last_decision import LastDecision  # noqa: PLC0415
        from ..models.normalised_content import NormalisedContent  # noqa: PLC0415

        d = dict(src_dict)
        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        id = UUID(d.pop("id"))

        received_at = datetime.datetime.fromisoformat(d.pop("received_at"))

        sensitivity = d.pop("sensitivity")

        source = d.pop("source")

        source_ref = d.pop("source_ref")

        status = d.pop("status")

        tenant_id = UUID(d.pop("tenant_id"))

        updated_at = datetime.datetime.fromisoformat(d.pop("updated_at"))

        def _parse_content(data: object) -> None | NormalisedContent | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                content_type_0 = NormalisedContent.from_dict(data)

                return content_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | NormalisedContent | Unset, data)

        content = _parse_content(d.pop("content", UNSET))

        def _parse_deadline_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                deadline_at_type_0 = datetime.datetime.fromisoformat(data)

                return deadline_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        deadline_at = _parse_deadline_at(d.pop("deadline_at", UNSET))

        def _parse_decision(data: object) -> DecisionItemOutDecisionType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                decision_type_0 = DecisionItemOutDecisionType0.from_dict(data)

                return decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecisionItemOutDecisionType0 | None | Unset, data)

        decision = _parse_decision(d.pop("decision", UNSET))

        def _parse_language(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        language = _parse_language(d.pop("language", UNSET))

        def _parse_last_decision(data: object) -> LastDecision | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                last_decision_type_0 = LastDecision.from_dict(data)

                return last_decision_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(LastDecision | None | Unset, data)

        last_decision = _parse_last_decision(d.pop("last_decision", UNSET))

        def _parse_niche(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        niche = _parse_niche(d.pop("niche", UNSET))

        def _parse_related_to(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                related_to_type_0 = UUID(data)

                return related_to_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        related_to = _parse_related_to(d.pop("related_to", UNSET))

        def _parse_risk(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        risk = _parse_risk(d.pop("risk", UNSET))

        def _parse_triage(data: object) -> DecisionItemOutTriageType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                triage_type_0 = DecisionItemOutTriageType0.from_dict(data)

                return triage_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(DecisionItemOutTriageType0 | None | Unset, data)

        triage = _parse_triage(d.pop("triage", UNSET))

        def _parse_urgency(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        urgency = _parse_urgency(d.pop("urgency", UNSET))

        decision_item_out = cls(
            created_at=created_at,
            id=id,
            received_at=received_at,
            sensitivity=sensitivity,
            source=source,
            source_ref=source_ref,
            status=status,
            tenant_id=tenant_id,
            updated_at=updated_at,
            content=content,
            deadline_at=deadline_at,
            decision=decision,
            language=language,
            last_decision=last_decision,
            niche=niche,
            related_to=related_to,
            risk=risk,
            triage=triage,
            urgency=urgency,
        )

        decision_item_out.additional_properties = d
        return decision_item_out

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
