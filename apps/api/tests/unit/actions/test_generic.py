"""Generic action bodies, run directly with a stub session (FR-40)."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.actions import generic
from app.actions.registry import ActionContext
from app.models.enums import JobKind
from app.workers import queue

ITEM = uuid.UUID("00000000-0000-0000-0000-000000000001")
TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
LOG = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


class StubSession:
    def __init__(self, item: Any = None) -> None:
        self.item = item

    async def get(self, model: Any, ident: Any) -> Any:
        return self.item


def ctx(session: Any = None) -> ActionContext:
    return ActionContext(
        session=session or StubSession(),
        tenant_id=TENANT,
        item_id=ITEM,
        option_id="A",
        action_log_id=LOG,
    )


async def test_archive_and_label_return_data() -> None:
    assert (await generic.archive(ctx(), generic.NoParams())).data == {"archived": True}
    out = await generic.label(ctx(), generic.LabelParams(label="urgent"))
    assert out.ok and out.data == {"label": "urgent"}


@pytest.mark.parametrize("fn", ["remind", "snooze"])
async def test_remind_and_snooze_enqueue_reminder_due(
    fn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake_enqueue(session: Any, **kwargs: Any) -> uuid.UUID:
        calls.append(kwargs)
        return uuid.uuid4()

    monkeypatch.setattr(queue, "enqueue", fake_enqueue)
    until = datetime.now(UTC) + timedelta(days=1)
    out = await getattr(generic, fn)(ctx(), generic.RemindParams(until=until))
    assert out.ok and out.data["until"] == until.isoformat()
    (call,) = calls
    assert call["kind"] == JobKind.ACTION and call["run_at"] == until
    assert call["payload"] == {"op": "reminder_due", "action_log_id": str(LOG)}
    assert call["item_id"] == ITEM and call["tenant_id"] == TENANT


async def test_create_task_defaults_title_from_item_content() -> None:
    session = StubSession(SimpleNamespace(content={"title": "Pay fees"}))
    out = await generic.create_task(ctx(session), generic.CreateTaskParams())
    assert out.data["task"]["title"] == "Pay fees"
    assert out.data["task"]["item_id"] == str(ITEM)


async def test_create_task_explicit_title_and_due() -> None:
    due = datetime(2030, 1, 1, tzinfo=UTC)
    out = await generic.create_task(ctx(), generic.CreateTaskParams(title="T", due=due))
    assert out.data["task"] == {"title": "T", "due": due.isoformat(), "item_id": str(ITEM)}


async def test_webhook_action_is_marker_for_action_done_event() -> None:
    out = await generic.webhook(ctx(), generic.NoParams())
    assert out.ok and out.data == {"delivers_via": "action.done"}
