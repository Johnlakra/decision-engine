"""triage_items against real Postgres: persistence, tenant settings, event (FR-20, FR-42)."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.models import Item, Job, Tenant, WebhookSubscription
from app.models.enums import JobKind
from app.models.tenant_settings import TenantSettings
from app.triage import service
from tests.fakes.fake_laya import FakeLayaClient
from tests.fakes.fake_llm import FakeLLM

pytestmark = pytest.mark.integration


async def test_triage_persists_record_and_emits_event(
    db_session: AsyncSession,
    tenant: Tenant,
    fake_llm: FakeLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "get_laya_client", lambda: FakeLayaClient(fail=True))
    db_session.add(TenantSettings(tenant_id=tenant.id, settings={"laya_mode": "shadow"}))
    db_session.add(
        WebhookSubscription(
            id=new_id(),
            tenant_id=tenant.id,
            url="https://example.com/h",
            events=["item.triaged"],
            secret_enc="x",
            enabled=True,
        )
    )
    item = Item(
        id=new_id(),
        tenant_id=tenant.id,
        source="manual",
        source_ref="t1",
        raw={},
        status="normalised",
        content={"title": "Invoice overdue", "body": "pay"},
    )
    db_session.add(item)
    await db_session.flush()
    fake_llm.script(
        "classify",
        {
            "needs_decision": {"choice": "A", "confidence": 0.8},
            "niche": {"choice": "generic", "confidence": 0.8},
            "urgency": {"level": 2, "confidence": 0.7},
            "risk": {"choice": "normal", "confidence": 0.9},
        },
    )
    outcomes = await service.triage_items(db_session, [item])
    await db_session.flush()
    assert outcomes[0].status == "triaged"
    assert item.triage["shadow"]["error"] == "laya_unavailable"
    jobs = (await db_session.execute(select(Job).where(Job.kind == JobKind.WEBHOOK.value))).all()
    assert len(jobs) == 1
