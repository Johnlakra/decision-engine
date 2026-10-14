"""Load and validate one niche YAML file (FR-70)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from app.niches.models import NicheConfig

NICHE_SCHEMA_FILE = "niche.schema.json"


class NicheValidationError(Exception):
    def __init__(self, file: str, json_pointer: str, message: str) -> None:
        super().__init__(f"{file}: {json_pointer or '/'}: {message}")
        self.file = file
        self.json_pointer = json_pointer
        self.message = message


def _pointer(parts: Any) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


@lru_cache(maxsize=8)
def _validator(schemas_dir: Path) -> Draft202012Validator:
    registry: Registry[Any] = Registry()
    for path in sorted(schemas_dir.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource)
        if "$id" in schema:
            registry = registry.with_resource(schema["$id"], resource)
    schema = json.loads((schemas_dir / NICHE_SCHEMA_FILE).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=registry)


def schema_errors(data: dict[str, Any], schemas_dir: Path) -> list[tuple[str, str]]:
    """Every JSON Schema violation as ``(json_pointer, message)``, sorted by pointer (ADR 0011)."""
    validator = _validator(schemas_dir.resolve())
    errors = sorted(validator.iter_errors(data), key=lambda e: _pointer(e.absolute_path))
    return [(_pointer(e.absolute_path), e.message) for e in errors]


def validate_niche_data(data: object, file: str, schemas_dir: Path) -> NicheConfig:
    """Validate raw data against the schema, then build the model."""
    if not isinstance(data, dict):
        raise NicheValidationError(file, "", "top level must be a mapping")
    errors = schema_errors(data, schemas_dir)
    if errors:
        pointer, message = errors[0]
        raise NicheValidationError(file, pointer, message)
    expected = Path(file).stem
    if data["name"] != expected:
        raise NicheValidationError(
            file, "/name", f"name {data['name']!r} must equal file name {expected!r}"
        )
    return NicheConfig.model_validate(data)


def load_niche_file(path: Path | str, schemas_dir: Path | str | None = None) -> NicheConfig:
    file_path = Path(path)
    if schemas_dir is None:
        from app.core.config import get_settings

        schemas_dir = get_settings().schemas_dir
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        raise NicheValidationError(file_path.name, "", f"cannot read YAML: {exc}") from exc
    return validate_niche_data(data, file_path.name, Path(schemas_dir))
