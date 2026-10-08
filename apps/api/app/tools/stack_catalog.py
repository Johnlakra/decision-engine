"""Stack catalog tools backed by ``data/stacks.yaml`` and ``data/free_tiers.yaml`` (FR-32, FR-71).

Both tools are local, so they are ``private_ok``. A missing or malformed data file raises, which
``run_tool`` turns into ``None`` (the decide step then runs without tool data).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.core.config import get_settings
from app.tools.registry import ToolResult, tool

TTL_S = 3600
MAX_STACKS = 6
SOURCE_STACKS = "data/stacks.yaml"
SOURCE_TIERS = "data/free_tiers.yaml"

SCORE_TYPE_MATCH = 4.0
SCORE_PER_SKILL = 2.0
SCORE_SKILL_CAP = 6.0
SCORE_NO_SKILL = -1.0
SCORE_BUDGET_OK = 2.0
SCORE_BUDGET_OVER = -5.0
SCORE_OFFLINE_FULL = 4.0
SCORE_OFFLINE_PARTIAL = 1.0
SCORE_OFFLINE_NONE = -6.0
SCORE_SCALE_OK = 1.0
SCORE_SCALE_OVER = -3.0
SCORE_LANG_OK = 1.0
SCORE_LANG_BAD = -1.0


class ShortlistArgs(BaseModel):
    project_type: str | None = None
    team_skills: list[str] = []
    budget_inr_month: float | None = None
    offline_needed: bool | None = None
    languages_needed: list[str] = []
    users_expected: int | None = None


class FreeTiersArgs(BaseModel):
    budget_inr_month: float | None = None
    project_type: str | None = None


def _load(data_dir: Path, filename: str, key: str) -> list[dict[str, Any]]:
    raw = yaml.safe_load((data_dir / filename).read_text(encoding="utf-8"))
    entries = raw[key]
    if not isinstance(entries, list):
        raise ValueError(f"{filename}: {key} must be a list")
    return entries


def load_stacks(data_dir: Path) -> list[dict[str, Any]]:
    return _load(data_dir, "stacks.yaml", "stacks")


def load_free_tiers(data_dir: Path) -> list[dict[str, Any]]:
    return _load(data_dir, "free_tiers.yaml", "free_tiers")


def _score(stack: dict[str, Any], args: ShortlistArgs) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if args.project_type and args.project_type != "other":
        score += SCORE_TYPE_MATCH
        reasons.append(f"built for {args.project_type}")
    if args.team_skills:
        wanted = {s.strip().lower() for s in args.team_skills}
        known = sorted(wanted & {s.lower() for s in stack["skills"]})
        if known:
            score += min(SCORE_PER_SKILL * len(known), SCORE_SKILL_CAP)
            reasons.append("team already knows " + ", ".join(known))
        else:
            score += SCORE_NO_SKILL
            reasons.append("new skills for the team")
    if args.budget_inr_month is not None:
        if stack["cost_inr_month"] <= args.budget_inr_month:
            score += SCORE_BUDGET_OK
            reasons.append("fits the budget")
        else:
            score += SCORE_BUDGET_OVER
            reasons.append("likely over budget")
    if args.offline_needed:
        offline = stack["offline"]
        score += {
            "full": SCORE_OFFLINE_FULL,
            "partial": SCORE_OFFLINE_PARTIAL,
        }.get(offline, SCORE_OFFLINE_NONE)
        reasons.append(f"offline support: {offline}")
    if args.users_expected is not None and stack["max_users"]:
        fits = args.users_expected <= stack["max_users"]
        score += SCORE_SCALE_OK if fits else SCORE_SCALE_OVER
        reasons.append("comfortable at this scale" if fits else "may outgrow the small tier")
    if any(lang != "en" for lang in args.languages_needed):
        score += SCORE_LANG_OK if stack["indic_ok"] else SCORE_LANG_BAD
        reasons.append("handles Indic text" if stack["indic_ok"] else "weak Indic support")
    return score, reasons or ["no requirements given; general-purpose pick"]


def _matches_type(stack: dict[str, Any], project_type: str | None) -> bool:
    if not project_type or project_type == "other":
        return True
    return project_type in stack["project_types"]


def shortlist_stacks(stacks: list[dict[str, Any]], args: ShortlistArgs) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for stack in stacks:
        if not _matches_type(stack, args.project_type):
            continue
        score, reasons = _score(stack, args)
        ranked.append(
            {
                "id": stack["id"],
                "name": stack["name"],
                "summary": stack["summary"],
                "score": score,
                "reasons": reasons,
                "cost_inr_month": stack["cost_inr_month"],
                "offline": stack["offline"],
                "risk": stack["risk"],
                "as_of": str(stack["as_of"]),
            }
        )
    ranked.sort(key=lambda s: (-s["score"], s["id"]))
    return ranked[:MAX_STACKS]


def _latest(entries: list[dict[str, Any]]) -> str | None:
    dates = [str(e["as_of"]) for e in entries]
    return max(dates) if dates else None


@tool("stack_catalog.shortlist", ttl_s=TTL_S, args=ShortlistArgs, private_ok=True)
async def shortlist(args: ShortlistArgs) -> ToolResult:
    stacks = shortlist_stacks(load_stacks(get_settings().data_dir), args)
    return ToolResult(
        name="stack_catalog.shortlist",
        data={"stacks": stacks},
        as_of=_latest(stacks),
        source=SOURCE_STACKS,
    )


@tool("stack_catalog.free_tiers", ttl_s=TTL_S, args=FreeTiersArgs, private_ok=True)
async def free_tiers(args: FreeTiersArgs) -> ToolResult:
    entries = load_free_tiers(get_settings().data_dir)
    if args.project_type and args.project_type != "other":
        entries = [e for e in entries if args.project_type in e["project_types"]]
    return ToolResult(
        name="stack_catalog.free_tiers",
        data={"entries": entries},
        as_of=_latest(entries),
        source=SOURCE_TIERS,
    )
