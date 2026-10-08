"""P1: school-ERP brief becomes a decision waiting for approval (FR-01, FR-24, FR-33)."""

import re

import pytest

pytest.importorskip("app.graph.run")
pytest.importorskip("app.ingest.service")
pytest.importorskip("app.tools.stack_catalog")

from app.tools.registry import run_tool  # noqa: E402
from tests.fakes.fake_laya import FakeLayaClient  # noqa: E402

from ._pipeline import load_item, post_item, run_worker_until_idle  # noqa: E402
from ._scripts import EXTRACTED, SCHOOL_ERP_BRIEF  # noqa: E402

pytestmark = pytest.mark.integration


async def test_school_erp_brief_ends_awaiting_approval_with_catalog_backed_options(
    client, account, factory, llm, use_laya
) -> None:  # type: ignore[no-untyped-def]
    # Arrange: Laya answers (shadow mode is the env default), the LLM fallback decides.
    laya = FakeLayaClient()
    use_laya(laya)

    # Act
    item_id = await post_item(client, account.key, text=SCHOOL_ERP_BRIEF, source_ref="p1-erp")
    await run_worker_until_idle(factory)

    # Assert: status, routing, decision shape (FR-01, FR-30)
    item = await load_item(factory, item_id)
    assert item.status == "awaiting_approval"
    assert item.niche == "tech_stack"
    assert item.decision is not None
    decision = item.decision
    option_ids = [o["id"] for o in decision["options"]]
    assert 2 <= len(option_ids) <= 5
    assert decision["recommended"] in option_ids
    assert len(re.split(r"(?<=[.!?])\s+", decision["rationale"].strip())) <= 3
    assert decision["autonomy"] == "suggest"

    # Assert: Laya shadow mode (FR-24): Laya was asked, the fallback answered
    assert item.triage is not None
    assert item.triage["mode"] == "shadow"
    assert item.triage["decided_by"] == "llm_fallback"
    assert laya.calls, "Laya must be called in shadow mode"

    # Assert: the decide prompt carries the real stack_catalog.shortlist output
    shortlist = await run_tool("stack_catalog.shortlist", EXTRACTED, sensitivity="public")
    assert shortlist is not None and shortlist.data["stacks"]
    top = shortlist.data["stacks"][0]
    marker = str(top.get("name") or top.get("id"))
    prompt = " ".join(str(m["content"]) for m in llm.calls_for("decide")[0].messages)
    assert marker in prompt
    assert SCHOOL_ERP_BRIEF not in {m["content"] for m in llm.calls_for("decide")[0].messages}, (
        "content must be fenced inside a larger message, never a bare message"
    )
