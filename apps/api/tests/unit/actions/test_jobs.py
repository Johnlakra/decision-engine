"""reminder_due job handler (FR-41)."""

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.actions import jobs

LOG = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
ITEM = uuid.UUID("00000000-0000-0000-0000-000000000001")
TENANT = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


class StubSession:
    def __init__(self, row: Any) -> None:
        self.row = row

    async def get(self, model: Any, ident: Any) -> Any:
        return self.row if ident == LOG else None


def job(payload: dict[str, Any]) -> Any:
    return SimpleNamespace(id=LOG, payload=payload, tenant_id=TENANT, item_id=ITEM)


async def test_reminder_due_emits_action_done(monkeypatch: pytest.MonkeyPatch) -> None:
    emitted: list[dict[str, Any]] = []

    async def fake_emit(session: Any, **kwargs: Any) -> None:
        emitted.append(kwargs)

    monkeypatch.setattr(jobs, "emit", fake_emit)
    row = SimpleNamespace(action="remind", tenant_id=TENANT, item_id=ITEM)
    await jobs.handle_action_job(
        StubSession(row),
        job({"op": "reminder_due", "action_log_id": str(LOG)}),  # type: ignore[arg-type]
    )
    (call,) = emitted
    assert call["event"] == "action.done"
    assert call["extra"] == {"action": "remind", "ok": True}
    assert call["item_id"] == ITEM and call["tenant_id"] == TENANT


async def test_missing_log_row_or_unknown_op_is_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*a: Any, **k: Any) -> None:
        raise AssertionError("must not emit")

    monkeypatch.setattr(jobs, "emit", boom)
    await jobs.handle_action_job(
        StubSession(None),
        job({"op": "reminder_due", "action_log_id": str(LOG)}),  # type: ignore[arg-type]
    )
    await jobs.handle_action_job(StubSession(None), job({"op": "nope"}))  # type: ignore[arg-type]
