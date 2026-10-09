"""Approving records time-to-decide and the correction in feedback (FR-54)."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Decision, Feedback, Tenant
from tests.fakes.fake_llm import FakeLLM, fake_llm  # noqa: F401
from tests.integration.graph_support import (
    mini_client,  # noqa: F401
    real_niches,  # noqa: F401
)
from tests.integration.test_decision_api import post, waiting_item

pytestmark = pytest.mark.integration

SessionFactory = async_sessionmaker[AsyncSession]


async def _only(factory: SessionFactory, model: type[Decision] | type[Feedback]):  # type: ignore[no-untyped-def]
    async with factory() as session:
        return (await session.scalars(select(model))).one()


async def test_approve_stores_time_to_decide_on_decision_and_feedback(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    assert (await post(mini_client, admin_key, item_id, {"verdict": "approve"})).status_code == 200

    decision = await _only(committed_db, Decision)
    feedback = await _only(committed_db, Feedback)
    assert decision.latency_ms is not None and decision.latency_ms >= 0
    assert feedback.kind == "decision"
    assert feedback.gold["decision"]["verdict"] == "approve"
    assert feedback.gold["decision"]["latency_ms"] == decision.latency_ms


async def test_reject_with_note_is_recorded_as_a_correction_label(
    mini_client: httpx.AsyncClient,  # noqa: F811
    committed_db: SessionFactory,
    tenant_committed: Tenant,
    admin_key: str,
    fake_llm: FakeLLM,  # noqa: F811
) -> None:
    item_id = await waiting_item(committed_db, tenant_committed, fake_llm)

    await post(mini_client, admin_key, item_id, {"verdict": "reject", "note": "not for us"})

    feedback = await _only(committed_db, Feedback)
    assert feedback.gold["decision"]["verdict"] == "reject"
    assert feedback.label_source == "human"
