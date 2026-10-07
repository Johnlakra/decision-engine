"""In-memory niche registry with last-good-version reload (FR-71)."""

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.niches.loader import NicheValidationError, load_niche_file
from app.niches.models import NicheConfig

log = logging.getLogger(__name__)
FALLBACK_NICHE = "generic"


@dataclass(frozen=True)
class NicheError:
    file: str
    json_pointer: str
    message: str


@dataclass(frozen=True)
class ReloadResult:
    loaded: list[str] = field(default_factory=list)
    errors: list[NicheError] = field(default_factory=list)


class MissingGenericNicheError(RuntimeError):
    """The generic fallback niche is absent and no previous version exists."""


class NicheRegistry:
    def __init__(self, niches_dir: Path | str, schemas_dir: Path | str) -> None:
        self._niches_dir = Path(niches_dir)
        self._schemas_dir = Path(schemas_dir)
        self._niches: dict[str, NicheConfig] = {}
        self._errors: list[NicheError] = []
        self._lock = threading.Lock()

    @property
    def errors(self) -> list[NicheError]:
        return list(self._errors)

    def get(self, name: str) -> NicheConfig | None:
        return self._niches.get(name)

    def all(self) -> list[NicheConfig]:
        return list(self._niches.values())

    def enabled(self) -> list[NicheConfig]:
        return [n for n in self._niches.values() if n.enabled]

    def reload(self, overrides: Mapping[str, dict[str, Any]] | None = None) -> ReloadResult:
        """Reload all files. Invalid files keep the previous version of that niche.

        `overrides` (DB rows by name) is reserved and unused in Phase 0.
        """
        with self._lock:
            return self._reload()

    def _reload(self) -> ReloadResult:
        errors: list[NicheError] = []
        fresh: dict[str, NicheConfig] = {}
        files = sorted(self._niches_dir.glob("*.yaml")) if self._niches_dir.is_dir() else []
        if not self._niches_dir.is_dir():
            errors.append(NicheError(str(self._niches_dir), "", "niches directory not found"))
        for path in files:
            try:
                cfg = load_niche_file(path, self._schemas_dir)
            except NicheValidationError as exc:
                log.error(
                    "niche_invalid file=%s pointer=%s: %s", exc.file, exc.json_pointer, exc.message
                )
                errors.append(NicheError(exc.file, exc.json_pointer, exc.message))
                continue
            fresh[cfg.name] = cfg
        # An invalid file keeps its previous version (by file stem == name).
        for path in files:
            stem = path.stem
            if stem not in fresh and stem in self._niches:
                fresh[stem] = self._niches[stem]
        if FALLBACK_NICHE not in fresh:
            errors.append(
                NicheError(f"{FALLBACK_NICHE}.yaml", "", "required fallback niche is missing")
            )
            previous = self._niches.get(FALLBACK_NICHE)
            if previous is None:
                self._errors = errors
                raise MissingGenericNicheError("generic niche is missing: cannot start")
            fresh[FALLBACK_NICHE] = previous
        self._niches = fresh
        self._errors = errors
        return ReloadResult(loaded=sorted(fresh), errors=errors)


_registry: NicheRegistry | None = None


def get_registry() -> NicheRegistry:
    global _registry
    if _registry is None:
        from app.core.config import get_settings

        settings = get_settings()
        registry = NicheRegistry(settings.niches_dir, settings.schemas_dir)
        registry.reload()
        _registry = registry
    return _registry


__all__ = [
    "NicheError",
    "NicheRegistry",
    "ReloadResult",
    "get_registry",
    "MissingGenericNicheError",
]
