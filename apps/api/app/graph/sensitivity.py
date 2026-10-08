"""Effective sensitivity for LLM routing (ADR 0005, FR-31)."""

from typing import Literal

from app.niches.models import NicheConfig

Sensitivity = Literal["public", "private"]


def effective_sensitivity(item_sensitivity: str, niche: NicheConfig) -> Sensitivity:
    """Private if the item or the routed niche is private. An item is never downgraded."""
    if item_sensitivity == "private" or niche.sensitivity == "private":
        return "private"
    return "public"
