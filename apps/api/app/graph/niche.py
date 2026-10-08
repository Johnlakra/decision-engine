"""Niche lookup for nodes: the routed niche, or ``generic`` when it vanished (FR-30, FR-71)."""

from app.niches.models import NicheConfig
from app.niches.registry import FALLBACK_NICHE, NicheRegistry, get_registry


def niche_for(name: str | None, registry: NicheRegistry | None = None) -> NicheConfig:
    reg = registry or get_registry()
    found = reg.get(name) if name else None
    if found is not None and found.enabled:
        return found
    fallback = reg.get(FALLBACK_NICHE)
    if fallback is None:
        raise RuntimeError("generic niche is not loaded")
    return fallback
