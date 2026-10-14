"""Server-side checks for ``PUT /v1/niches/{name}`` (ADR 0009 section 3, ADR 0011)."""

from typing import Any

from pydantic import ValidationError

from app.actions import registered as registered_actions
from app.niches.loader import schema_errors
from app.niches.models import NicheConfig
from app.niches.registry import FALLBACK_NICHE, NicheRegistry
from app.tools.registry import registered as registered_tools

MAX_ERRORS = 20
Issue = tuple[str, str]  # (json_pointer, message)


def _unregistered(config: NicheConfig, baseline: NicheConfig | None) -> list[Issue]:
    """Registry checks for entries this PUT adds; entries already in the baseline may stay.

    ADR 0009 amendment: baseline = effective config before the PUT (empty for a new niche).
    """
    issues: list[Issue] = []
    known_actions, known_tools = registered_actions(), registered_tools()
    base_actions = set(baseline.actions) if baseline else set()
    base_tools = set(baseline.tools) if baseline else set()
    base_auto = set(baseline.auto_actions) if baseline else set()
    for index, item in enumerate(config.actions):
        if item not in known_actions and item not in base_actions:
            issues.append((f"/actions/{index}", f"action {item!r} is not registered"))
    for index, item in enumerate(config.tools):
        if item not in known_tools and item not in base_tools:
            issues.append((f"/tools/{index}", f"tool {item!r} is not registered"))
    for index, item in enumerate(config.auto_actions):
        if item in config.actions:
            continue
        if item not in base_auto or item in base_actions:  # added, or its action was removed
            issues.append((f"/auto_actions/{index}", f"auto action {item!r} is not in actions"))
    return issues


def _floor(config: NicheConfig, shipped: NicheConfig | None) -> list[Issue]:
    """The shipped YAML sets the safety floor; an override may be stricter, never weaker."""
    if shipped is None:
        return []
    issues: list[Issue] = []
    review = config.expert_review
    if shipped.expert_review.always and not review.always:
        issues.append(("/expert_review/always", "expert review is required by the shipped niche"))
    if shipped.expert_review.when_topics and not (review.always or review.when_topics):
        issues.append(
            ("/expert_review", "expert review topics of the shipped niche cannot be removed")
        )
    if shipped.expert_review.always or shipped.expert_review.when_topics:
        if config.autonomy != "ask":
            issues.append(
                ("/autonomy", "autonomy must stay 'ask' (shipped niche needs expert review)")
            )
    if shipped.sensitivity == "private" and config.sensitivity != "private":
        issues.append(("/sensitivity", "this niche must stay private"))
    return issues


def _semantic(
    name: str, config: NicheConfig, shipped: NicheConfig | None, baseline: NicheConfig | None
) -> list[Issue]:
    issues: list[Issue] = []
    if config.name != name:
        issues.append(("/name", f"name {config.name!r} must equal the path name {name!r}"))
    if name == FALLBACK_NICHE and not config.enabled:
        issues.append(("/enabled", "the generic niche cannot be disabled"))
    if config.steps:
        issues.append(("/steps", "custom steps need a new ADR; leave steps empty"))
    return [*issues, *_unregistered(config, baseline), *_floor(config, shipped)]


def _pydantic_issues(exc: ValidationError) -> list[Issue]:
    return [("".join(f"/{part}" for part in e["loc"]), e["msg"]) for e in exc.errors()]


def validate_override(
    name: str, body: object, registry: NicheRegistry, baseline: NicheConfig | None = None
) -> list[Issue]:
    """All problems, sorted by pointer, max 20; empty means the body may be saved.

    ``baseline`` is the effective config before the PUT (None: new niche, every entry is new).
    Semantic checks run only when the schema passes (they assume valid types).
    """
    if not isinstance(body, dict):
        return [("", "body must be a JSON object")]
    issues = schema_errors(body, registry.schemas_dir)
    if not issues:
        try:
            config = NicheConfig.model_validate(body)
        except ValidationError as exc:
            issues = _pydantic_issues(exc)
        else:
            issues = _semantic(name, config, registry.yaml_config(name), baseline)
    return sorted(issues, key=lambda issue: issue[0])[:MAX_ERRORS]


def as_json(config: NicheConfig) -> dict[str, Any]:
    """Effective config as a JSON object that passes the schema again (nulls dropped)."""
    return config.model_dump(mode="json", exclude_none=True)
