"""Niche routes: list, read, write DB overrides, reload (FR-70, FR-71; ADR 0009, 0011)."""

from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_scope
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.db.session import get_session
from app.models import TenantSettings
from app.niches import overrides
from app.niches.models import NicheConfig
from app.niches.registry import MissingGenericNicheError, NicheError, NicheRegistry, get_registry
from app.niches.rules import as_json, validate_override
from app.schemas.niches import NicheDetail, NicheList, NicheRow
from app.security.api_keys import Principal
from app.triage.modes import resolve_mode

router = APIRouter(prefix="/niches", tags=["niches"])

Reader = Annotated[Principal, Depends(require_scope("items:read"))]
Admin = Annotated[Principal, Depends(require_scope("admin"))]
Session = Annotated[AsyncSession, Depends(get_session)]

NICHE_BODY_EXAMPLE = {
    "name": "news_radar",
    "label": "News radar",
    "description": "a news story or article worth reading, saving or acting on",
    "enabled": True,
    "autonomy": "ask",
    "prompt": "Summarize the story and decide whether the owner should read, save or skip it.",
    "actions": ["create_task"],
    "auto_actions": [],
}


class ReloadResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"loaded": ["generic", "inbox", "news_radar", "tech_stack"]}]
        }
    )

    loaded: list[str]
    errors: list[dict[str, str]] = []


def _error_dicts(errors: list[NicheError]) -> list[dict[str, Any]]:
    return [{"file": e.file, "json_pointer": e.json_pointer, "message": e.message} for e in errors]


def _row(cfg: NicheConfig, registry: NicheRegistry, tenant_settings: dict[str, Any]) -> NicheRow:
    return NicheRow(
        name=cfg.name,
        label=cfg.label,
        description=cfg.description,
        enabled=cfg.enabled,
        autonomy=cfg.autonomy,
        auto_actions=cfg.auto_actions,
        source="db" if registry.source(cfg.name) == "db" else "yaml",
        version=cfg.version,
        laya_mode=resolve_mode(tenant_settings, cfg.name, get_settings().laya_mode),
    )


def _detail(cfg: NicheConfig, registry: NicheRegistry) -> NicheDetail:
    source = "db" if registry.source(cfg.name) == "db" else "yaml"
    config = as_json(cfg)
    text = registry.yaml_text(cfg.name) if source == "yaml" else None
    if text is None:
        text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    return NicheDetail(name=cfg.name, source=source, version=cfg.version, config=config, yaml=text)


@router.get(
    "",
    response_model=NicheList,
    summary="List niches",
    operation_id="list_niches",
)
async def list_niches(principal: Reader, session: Session) -> NicheList:
    registry = get_registry()
    await overrides.sync_registry(session, registry)
    row = await session.get(TenantSettings, principal.tenant_id)
    tenant_settings = dict(row.settings) if row is not None else {}
    rows = [_row(cfg, registry, tenant_settings) for cfg in registry.all()]
    return NicheList(data=sorted(rows, key=lambda r: r.name))


@router.get(
    "/{name}",
    response_model=NicheDetail,
    summary="Read one niche (effective config and its YAML text)",
    operation_id="get_niche",
    responses={404: {"description": "Unknown niche"}},
)
async def get_niche(name: str, principal: Reader, session: Session) -> NicheDetail:
    registry = get_registry()
    await overrides.sync_registry(session, registry)
    cfg = registry.get(name)
    if cfg is None:
        raise ProblemError(404, "Not Found", f"Niche {name!r} not found")
    return _detail(cfg, registry)


@router.put(
    "/{name}",
    response_model=NicheDetail,
    summary="Save a DB override for a niche (one complete config)",
    operation_id="put_niche",
    responses={
        403: {"description": "API key lacks the admin scope"},
        422: {
            "description": "Validation errors; nothing was saved",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Niche validation failed",
                        "status": 422,
                        "detail": "1 problem; nothing was saved",
                        "errors": [
                            {
                                "json_pointer": "/autonomy",
                                "message": "'yolo' is not one of ['suggest', 'ask', 'auto']",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def put_niche(
    name: str,
    principal: Admin,
    session: Session,
    body: Annotated[Any, Body(examples=[NICHE_BODY_EXAMPLE])] = None,
) -> NicheDetail:
    registry = get_registry()
    await overrides.sync_registry(session, registry)
    issues = validate_override(name, body, registry, registry.get(name))
    if issues:
        raise ProblemError(
            422,
            "Niche validation failed",
            f"{len(issues)} problem{'s' if len(issues) != 1 else ''}; nothing was saved",
            errors=[{"json_pointer": p, "message": m} for p, m in issues],
        )
    await overrides.save_override(session, principal.tenant_id, body)
    await session.commit()
    await overrides.sync_registry(session, registry)
    cfg = registry.get(name)
    if cfg is None or registry.source(name) != "db":
        raise ProblemError(
            500, "Niche not applied", "The override was saved but could not be loaded"
        )
    return _detail(cfg, registry)


@router.post(
    "/reload",
    response_model=ReloadResponse,
    summary="Reload niche configs from disk and re-apply DB overrides",
    operation_id="reload_niches",
    responses={
        403: {"description": "API key lacks the admin scope"},
        422: {
            "description": "Validation errors; the previous niche set is still served",
            "content": {
                "application/problem+json": {
                    "example": {
                        "type": "about:blank",
                        "title": "Niche validation failed",
                        "status": 422,
                        "detail": "1 niche file(s) are invalid; previous versions stay active",
                        "errors": [
                            {
                                "file": "inbox.yaml",
                                "json_pointer": "/autonomy",
                                "message": "'yolo' is not one of ['ask', 'auto']",
                            }
                        ],
                    }
                }
            },
        },
    },
)
async def reload_niches(_: Admin, session: Session) -> ReloadResponse:
    registry = get_registry()
    try:
        result = await overrides.reload_registry(session, registry)
    except MissingGenericNicheError as exc:
        raise ProblemError(
            422,
            "Niche validation failed",
            str(exc),
            errors=_error_dicts(registry.errors),
        ) from exc
    if result.errors:
        raise ProblemError(
            422,
            "Niche validation failed",
            f"{len(result.errors)} niche problem(s); previous versions stay active",
            errors=_error_dicts(result.errors),
        )
    return ReloadResponse(loaded=result.loaded)
