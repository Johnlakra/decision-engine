"""In-memory niche registry with last-good-version reload (FR-71)."""

import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.niches.loader import NicheValidationError, load_niche_file, validate_niche_data
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
        self._yaml: dict[str, NicheConfig] = {}  # last good shipped version of each file
        self._sources: dict[str, str] = {}
        self._errors: list[NicheError] = []
        self._lock = threading.Lock()
        # Fingerprint of the DB overrides last applied (ADR 0009); None = never synced.
        self.fingerprint: tuple[int, int, datetime | None] | None = None

    @property
    def errors(self) -> list[NicheError]:
        return list(self._errors)

    @property
    def niches_dir(self) -> Path:
        return self._niches_dir

    @property
    def schemas_dir(self) -> Path:
        return self._schemas_dir

    def source(self, name: str) -> str:
        """``"db"`` when a DB override is effective, else ``"yaml"``."""
        return self._sources.get(name, "yaml")

    def yaml_config(self, name: str) -> NicheConfig | None:
        """The shipped YAML version of ``name`` (ignoring overrides), for the safety floor."""
        return self._yaml.get(name)

    def yaml_text(self, name: str) -> str | None:
        path = self._niches_dir / f"{name}.yaml"
        try:
            return path.read_text(encoding="utf-8") if path.is_file() else None
        except (OSError, UnicodeDecodeError):
            return None

    def get(self, name: str) -> NicheConfig | None:
        return self._niches.get(name)

    def all(self) -> list[NicheConfig]:
        return list(self._niches.values())

    def enabled(self) -> list[NicheConfig]:
        return [n for n in self._niches.values() if n.enabled]

    def reload(self, overrides: Mapping[str, dict[str, Any]] | None = None) -> ReloadResult:
        """Reload all files, then apply DB ``overrides`` (complete configs by name).

        Invalid files keep the previous version of that niche. An invalid override is skipped:
        the YAML (or previous good) version stays and the error is reported as ``db:<name>``.
        """
        with self._lock:
            return self._reload(overrides or {})

    def _reload(self, overrides: Mapping[str, dict[str, Any]]) -> ReloadResult:
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
            if stem not in fresh and stem in self._yaml:
                fresh[stem] = self._yaml[stem]
        yaml_good = dict(fresh)
        sources = {name: "yaml" for name in fresh}
        for name in sorted(overrides):
            try:
                fresh[name] = self._validate_override(name, overrides[name])
                sources[name] = "db"
            except NicheValidationError as exc:
                log.error("niche_override_invalid name=%s pointer=%s", name, exc.json_pointer)
                errors.append(NicheError(f"db:{name}", exc.json_pointer, exc.message))
                if name not in fresh and self._sources.get(name) == "db" and name in self._niches:
                    fresh[name] = self._niches[name]  # DB-only niche: keep the last good one
                    sources[name] = "db"
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
        self._yaml = yaml_good
        self._sources = sources
        self._errors = errors
        return ReloadResult(loaded=sorted(fresh), errors=errors)

    def _validate_override(self, name: str, config: dict[str, Any]) -> NicheConfig:
        try:
            return validate_niche_data(config, f"{name}.yaml", self._schemas_dir)
        except ValidationError as exc:
            first = exc.errors()[0]
            pointer = "".join("/" + str(part) for part in first["loc"])
            raise NicheValidationError(f"db:{name}", pointer, first["msg"]) from exc


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
