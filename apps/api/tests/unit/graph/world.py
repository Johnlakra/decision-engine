"""A stateful in-memory stand-in for the graph's DB access (store + store_approval)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.graph import store, store_approval
from app.graph.errors import InvalidDecision, NotAwaitingApproval
from app.graph.nodes import decide as decide_mod
from app.models.enums import DecidedBy, ItemStatus, Verdict
from app.models.status import transition
from app.schemas.decision import DecisionIn

TRIAGE = {
    "mode": "on",
    "decided_by": "laya",
    "answers": {
        "needs_decision": {
            "type": "choice",
            "choice": "A",
            "confidence": 0.95,
            "source": "llm_fallback",
        },
        "niche": {
            "type": "choice",
            "choice": "generic",
            "confidence": 0.95,
            "source": "llm_fallback",
        },
    },
    "questions": {},
    "fallback": True,
    "latency_ms": 1,
}

DECISION_OUT: dict[str, Any] = {
    "options": [
        {"id": "A", "label": "Archive it", "actions": [{"type": "archive"}]},
        {"id": "B", "label": "Remind me", "actions": [{"type": "remind", "params": {}}]},
    ],
    "recommended": "A",
    "rationale": "Low value.",
    "confidence": 0.8,
}


class World:
    def __init__(self, **view: Any) -> None:
        self.item = SimpleNamespace(status="triaged")
        self.view_fields: dict[str, Any] = {
            "id": "i1",
            "tenant_id": "t1",
            "source": "manual",
            "sensitivity": "public",
            "language": "en",
            "niche": None,
            "risk": "normal",
            "triage": TRIAGE,
            "content": {"title": "Brief", "body": "We need a decision"},
            **view,
        }
        self.decision: dict[str, Any] | None = None
        self.decisions: list[dict[str, Any]] = []
        self.feedback: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.jobs: list[dict[str, Any]] = []
        self.executed: list[dict[str, Any]] = []

    # store ---------------------------------------------------------------------------------
    async def load_item_view(self, item_id: str) -> store.ItemView:
        return store.ItemView(status=self.item.status, decision=self.decision, **self.view_fields)

    async def apply_route(self, item_id: str, *, niche: str, informational: bool) -> None:
        self.view_fields["niche"] = niche
        if self.item.status == ItemStatus.TRIAGED:
            transition(
                self.item, ItemStatus.INFORMATIONAL if informational else ItemStatus.DECIDING
            )

    async def save_entities(self, item_id: str, entities: dict[str, Any]) -> None:
        self.view_fields["content"] = {**self.view_fields["content"], "entities": entities}

    async def save_decision(self, item_id: str, decision: dict[str, Any]) -> None:
        if self.item.status == ItemStatus.DECIDING:
            self.decision = decision

    async def load_corrections(
        self, tenant_id: str, niche: str, limit: int, *, sensitivity: str = "public"
    ) -> list[Any]:
        return []

    # store_approval --------------------------------------------------------------------------
    async def mark_ready(self, item_id: str, *, announce: bool) -> dict[str, Any]:
        decision = dict(self.decision or {})
        if self.item.status == ItemStatus.DECIDING:
            decision["ready_at"] = datetime.now(UTC).isoformat()
            self.decision = decision
            transition(self.item, ItemStatus.AWAITING_APPROVAL)
            if announce:
                self.events.append("decision.ready")
        return decision

    async def record_verdict(
        self, item_id: str, body: DecisionIn, *, decided_by: DecidedBy
    ) -> dict[str, Any]:
        if self.item.status != ItemStatus.AWAITING_APPROVAL:
            if not self.decisions:
                raise NotAwaitingApproval(self.item.status)
            return self.decisions[-1]
        ids = [o["id"] for o in (self.decision or {})["options"]]
        option = body.option or (
            (self.decision or {})["recommended"]
            if body.verdict in (Verdict.APPROVE, Verdict.EDIT)
            else None
        )
        if option is not None and option not in ids:
            raise InvalidDecision(option)
        target = {
            Verdict.APPROVE: ItemStatus.APPROVED,
            Verdict.EDIT: ItemStatus.APPROVED,
            Verdict.REJECT: ItemStatus.REJECTED,
            Verdict.SNOOZE: ItemStatus.SNOOZED,
        }[body.verdict]
        if decided_by == DecidedBy.AUTO and target == ItemStatus.APPROVED:
            target = ItemStatus.AUTO_APPROVED
        transition(self.item, target)
        verdict = {
            "verdict": body.verdict.value,
            "option": option,
            "edits": body.edits,
            "decided_by": decided_by.value,
        }
        self.decisions.append(verdict)
        self.feedback.append({"verdict": body.verdict.value})
        self.events.append("decision.made")
        if body.verdict == Verdict.SNOOZE:
            self.jobs.append({"op": "unsnooze", "run_at": body.snooze_until})
        return verdict

    async def execute_actions(
        self,
        item_id: str,
        tenant_id: str,
        option_id: str | None,
        actions: list[dict[str, Any]],
        *,
        run: bool,
    ) -> list[dict[str, Any]]:
        if self.item.status in (ItemStatus.APPROVED, ItemStatus.AUTO_APPROVED):
            transition(self.item, ItemStatus.ACTING)
        elif self.item.status != ItemStatus.ACTING:
            return []
        done = []
        for spec in actions if run else []:
            self.executed.append(spec)
            self.events.append("action.done")
            done.append({"action": spec["type"], "ok": True, "error": None})
        transition(self.item, ItemStatus.DONE)
        return done

    async def complete_item(self, item_id: str) -> None:
        if self.item.status in (ItemStatus.REJECTED, ItemStatus.INFORMATIONAL):
            transition(self.item, ItemStatus.DONE)

    def unsnooze(self) -> None:
        transition(self.item, ItemStatus.AWAITING_APPROVAL)


def install_world(monkeypatch: pytest.MonkeyPatch, world: World) -> World:
    for name in (
        "load_item_view",
        "apply_route",
        "save_entities",
        "save_decision",
        "load_corrections",
    ):
        monkeypatch.setattr(store, name, getattr(world, name))
    for name in ("mark_ready", "record_verdict", "execute_actions", "complete_item"):
        monkeypatch.setattr(store_approval, name, getattr(world, name))
    monkeypatch.setattr(decide_mod, "registered_actions", lambda: None)
    return world


FUTURE = lambda: datetime.now(UTC) + timedelta(hours=1)  # noqa: E731
