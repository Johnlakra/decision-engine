"""stack_catalog tools (FR-32, FR-71)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.config import REPO_ROOT
from app.tools import registry, stack_catalog
from app.tools.registry import registered, run_tool

SCHOOL_ERP: dict[str, Any] = {
    "project_type": "mobile_app",
    "team_size": 3,
    "team_skills": ["python", "react"],
    "budget_inr_month": 0,
    "users_expected": 2000,
    "offline_needed": True,
    "languages_needed": ["en", "hi", "pa"],
}


@pytest.fixture(autouse=True)
def _clear_cache() -> Iterator[None]:
    registry._CACHE.clear()
    yield
    registry._CACHE.clear()


def test_tools_registered_by_import() -> None:
    assert {"stack_catalog.shortlist", "stack_catalog.free_tiers"} <= registered()


async def test_offline_zero_budget_ranks_offline_first_stack_in_top3() -> None:
    result = await run_tool("stack_catalog.shortlist", SCHOOL_ERP, sensitivity="public")

    assert result is not None
    stacks = result.data["stacks"]
    assert 0 < len(stacks) <= 6
    top3 = stacks[:3]
    assert all(s["offline"] == "full" for s in top3)
    assert any(s["id"].startswith("expo_") for s in top3)
    assert all(s["reasons"] and "score" in s and s["as_of"] for s in stacks)
    assert [s["score"] for s in stacks] == sorted((s["score"] for s in stacks), reverse=True)
    assert result.as_of and result.source


async def test_shortlist_is_private_ok() -> None:
    result = await run_tool("stack_catalog.shortlist", SCHOOL_ERP, sensitivity="private")
    assert result is not None


async def test_shortlist_all_args_optional() -> None:
    result = await run_tool("stack_catalog.shortlist", {}, sensitivity="public")
    assert result is not None and result.data["stacks"]


async def test_shortlist_respects_project_type() -> None:
    result = await run_tool(
        "stack_catalog.shortlist", {"project_type": "data_pipeline"}, sensitivity="public"
    )
    assert result is not None
    catalog = {s["id"]: s for s in stack_catalog.load_stacks(REPO_ROOT / "data")}
    assert all("data_pipeline" in catalog[s["id"]]["project_types"] for s in result.data["stacks"])


async def test_budget_over_limit_ranks_cheaper_stack_higher() -> None:
    cheap = stack_catalog.shortlist_stacks(
        stack_catalog.load_stacks(REPO_ROOT / "data"),
        stack_catalog.ShortlistArgs(project_type="web_app", budget_inr_month=0),
    )
    assert cheap[0]["cost_inr_month"] == 0


async def test_skill_match_prefers_known_language() -> None:
    result = await run_tool(
        "stack_catalog.shortlist",
        {"project_type": "api", "team_skills": ["Go"]},
        sensitivity="public",
    )
    assert result is not None
    assert result.data["stacks"][0]["id"].startswith("go_")


async def test_free_tiers_have_as_of_and_source() -> None:
    result = await run_tool(
        "stack_catalog.free_tiers", {"project_type": "web_app"}, sensitivity="public"
    )
    assert result is not None
    entries = result.data["entries"]
    assert entries
    assert all(e["as_of"] and e["source_url"].startswith("https://") for e in entries)
    assert result.as_of


def test_data_files_every_entry_dated_and_unique() -> None:
    stacks = yaml.safe_load((REPO_ROOT / "data" / "stacks.yaml").read_text())["stacks"]
    tiers = yaml.safe_load((REPO_ROOT / "data" / "free_tiers.yaml").read_text())["free_tiers"]
    assert 28 <= len(stacks) <= 36
    assert len({s["id"] for s in stacks}) == len(stacks)
    assert all(s["as_of"] for s in stacks)
    assert all(t["as_of"] and t["source_url"].startswith("https://") for t in tiers)


async def test_missing_data_file_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Fake:
        data_dir = tmp_path

    monkeypatch.setattr(stack_catalog, "get_settings", lambda: Fake())

    short = await run_tool("stack_catalog.shortlist", SCHOOL_ERP, sensitivity="public")
    tiers = await run_tool("stack_catalog.free_tiers", {}, sensitivity="public")

    assert short is None and tiers is None
