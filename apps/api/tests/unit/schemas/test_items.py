"""C1 public item shape never leaks raw or hints (FR-02, ADR 0004)."""

import uuid
from datetime import UTC, datetime

from app.models import Decision, Item
from app.schemas.items import item_to_public


def _item() -> Item:
    now = datetime.now(UTC)
    return Item(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), source="manual", source_ref="r1",
        received_at=now, status="triaged", raw={"secret": "payload"},
        content={"title": "Fee due", "body": "pay"}, language="en", sensitivity="public",
        niche="generic", triage={"mode": "shadow"}, decision=None, risk="normal", urgency=1,
        hints={"title": "hint"}, callback_url="https://x.io/cb", created_at=now, updated_at=now,
    )  # fmt: skip


def test_public_item_has_no_raw_or_hints() -> None:
    dumped = item_to_public(_item(), None).model_dump(mode="json")
    flat = repr(dumped)
    for forbidden in ("raw", "hints", "callback_url", "secret", "https://x.io/cb"):
        assert forbidden not in flat
    assert dumped["content"]["title"] == "Fee due"
    assert dumped["last_decision"] is None


def test_last_decision_mapped() -> None:
    item = _item()
    decided = datetime.now(UTC)
    decision = Decision(
        id=uuid.uuid4(), tenant_id=item.tenant_id, item_id=item.id, verdict="approve",
        option="A", decided_by="human", created_at=decided, updated_at=decided,
    )  # fmt: skip
    out = item_to_public(item, decision)
    assert out.last_decision is not None
    assert out.last_decision.verdict == "approve"
    assert out.last_decision.decided_at == decided


def test_item_without_content_serialises() -> None:
    item = _item()
    item.content = None
    assert item_to_public(item, None).content is None
