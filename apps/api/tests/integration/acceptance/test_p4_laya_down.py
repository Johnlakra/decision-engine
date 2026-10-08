"""P4: Laya down never loses an item (FR-24, NFR-03)."""

import pytest
from sqlalchemy import func, select

pytest.importorskip("app.graph.run")
pytest.importorskip("app.triage.service")
pytest.importorskip("app.tools.stack_catalog")

from app.models import Item, Job  # noqa: E402
from app.triage.laya_client import HttpLayaClient  # noqa: E402
from tests.fakes.fake_laya import FakeLayaClient  # noqa: E402
from tests.fakes.fake_llm import Failure  # noqa: E402

from ._pipeline import load_item, post_item, run_worker_until_idle  # noqa: E402
from ._scripts import SCHOOL_ERP_BRIEF  # noqa: E402
from .conftest import closed_port  # noqa: E402

pytestmark = pytest.mark.integration

SETTLED = {"awaiting_approval", "needs_human_triage"}


async def test_shadow_mode_with_laya_down_falls_back_to_llm(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient(fail=True))
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p4a")
    await run_worker_until_idle(factory)

    item = await load_item(factory, item_id)
    assert item.triage is not None
    assert item.triage["decided_by"] == "llm_fallback"
    assert item.triage["shadow"]["error"] == "laya_unavailable"
    assert item.status == "awaiting_approval"


async def test_on_mode_with_laya_down_falls_back_to_llm(
    client, account, factory, llm, use_laya, set_laya_mode
) -> None:  # type: ignore[no-untyped-def]
    await set_laya_mode("on")  # explicit tenant setting; nothing defaults to on
    use_laya(FakeLayaClient(fail=True))
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p4b")
    await run_worker_until_idle(factory)

    item = await load_item(factory, item_id)
    assert item.triage is not None
    assert item.triage["mode"] == "on"
    assert item.triage["decided_by"] == "llm_fallback"


async def test_laya_and_llm_both_down_waits_for_human_triage(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    use_laya(FakeLayaClient(fail=True))
    llm.script("classify", Failure.TIMEOUT, repeat=True)
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p4c")
    await run_worker_until_idle(factory)

    item = await load_item(factory, item_id)
    assert item.status == "needs_human_triage"
    async with factory() as session:
        job_statuses = (
            await session.scalars(select(Job.status).where(Job.item_id == item.id))
        ).all()
    assert job_statuses and set(job_statuses) == {"done"}, "the job must finish, not fail or retry"


async def test_ten_items_with_laya_unreachable_none_lost(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    unreachable = HttpLayaClient(f"http://127.0.0.1:{closed_port()}", "key", 1.0)
    use_laya(unreachable)
    for index in range(10):
        await post_item(
            client, account.key, text=f"{SCHOOL_ERP_BRIEF} #{index}", source_ref=f"p4d-{index}"
        )
    await run_worker_until_idle(factory)
    await unreachable.aclose()

    async with factory() as session:
        total = await session.scalar(select(func.count()).select_from(Item))
        statuses = (await session.scalars(select(Item.status))).all()
    assert total == 10
    assert set(statuses) <= SETTLED, statuses
