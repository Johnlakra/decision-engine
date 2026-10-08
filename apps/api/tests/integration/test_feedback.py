"""Feedback write and export against Postgres (FR-54, FR-80)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.feedback.export import iter_export
from app.feedback.service import record_decision_feedback
from app.models import Item, Tenant
from app.models.enums import DecidedBy, Verdict
from app.schemas.decision import DecisionIn

pytestmark = pytest.mark.integration

Q = {"k": {"type": "choice", "instructions": "keep it?", "criteria": {"A": "y", "B": "n"}}}


async def test_one_decision_one_row_and_export(db_session: AsyncSession, tenant: Tenant) -> None:
    item = Item(
        id=new_id(),
        tenant_id=tenant.id,
        source="manual",
        source_ref="fb1",
        raw={"secret": "x"},
        niche="inbox",
        content={"title": "Hello", "body": "b" * 2000},
        triage={"questions": Q, "answers": {"k": {"type": "choice", "choice": "B"}}},
    )
    db_session.add(item)
    await db_session.flush()
    await record_decision_feedback(
        db_session,
        item=item,
        body=DecisionIn(verdict=Verdict.REJECT),
        decided_by=DecidedBy.HUMAN,
        latency_ms=10,
    )
    lines = [
        line
        async for line in iter_export(
            db_session, tenant_id=tenant.id, niche="inbox", fmt="laya_eval", since=None
        )
    ]
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["expected"] == {"k": "B"} and len(row["state"]) <= 700 and "raw" not in row
    later = datetime.now(UTC) + timedelta(days=1)
    assert [
        line
        async for line in iter_export(
            db_session, tenant_id=tenant.id, niche="inbox", fmt="laya_train", since=later
        )
    ] == []
