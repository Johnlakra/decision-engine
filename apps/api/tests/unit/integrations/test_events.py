"""emit() decides on subscriptions and enqueues a fan-out job (FR-42, contract C2)."""

import uuid
from typing import Any

import pytest

from app.integrations import events
from app.models.enums import JobKind


class FakeResult:
    def __init__(self, value: bool) -> None:
        self._value = value

    def scalar(self) -> bool:
        return self._value


class FakeSession:
    def __init__(self, has_subscription: bool) -> None:
        self.has_subscription = has_subscription
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.has_subscription)


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(session: Any, **kwargs: Any) -> uuid.UUID:
        calls.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(events.queue, "enqueue", fake_enqueue)
    return calls


async def test_no_subscription_writes_nothing(enqueued: list[dict[str, Any]]) -> None:
    session = FakeSession(has_subscription=False)
    await events.emit(
        session,  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        event="item.triaged",
        item_id=uuid.uuid4(),
    )
    assert enqueued == []


async def test_matching_subscription_enqueues_fanout(enqueued: list[dict[str, Any]]) -> None:
    tenant_id, item_id = uuid.uuid4(), uuid.uuid4()
    await events.emit(
        FakeSession(has_subscription=True),  # type: ignore[arg-type]
        tenant_id=tenant_id,
        event="decision.made",
        item_id=item_id,
        extra={"verdict": "approve"},
    )
    assert len(enqueued) == 1
    call = enqueued[0]
    assert call["kind"] is JobKind.WEBHOOK
    assert call["tenant_id"] == tenant_id
    assert call["item_id"] == item_id
    payload = call["payload"]
    assert payload["op"] == "fanout"
    assert payload["event"] == "decision.made"
    assert payload["extra"] == {"verdict": "approve"}
    assert payload["event_id"].startswith("evt_")
    assert uuid.UUID(payload["event_id"][4:]).version == 7


async def test_extra_defaults_to_empty_dict(enqueued: list[dict[str, Any]]) -> None:
    await events.emit(
        FakeSession(has_subscription=True),  # type: ignore[arg-type]
        tenant_id=uuid.uuid4(),
        event="action.done",
        item_id=uuid.uuid4(),
    )
    assert enqueued[0]["payload"]["extra"] == {}


async def test_event_ids_are_unique(enqueued: list[dict[str, Any]]) -> None:
    session = FakeSession(has_subscription=True)
    for _ in range(2):
        await events.emit(
            session,  # type: ignore[arg-type]
            tenant_id=uuid.uuid4(),
            event="decision.ready",
            item_id=uuid.uuid4(),
        )
    assert enqueued[0]["payload"]["event_id"] != enqueued[1]["payload"]["event_id"]
