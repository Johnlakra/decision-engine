"""Liveness probe: no database, no Redis (NFR-08)."""

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_principal
from app.db.redis import ping_redis
from app.db.session import get_session
from app.llm import gateway
from app.niches.registry import get_registry
from app.security.api_keys import Principal
from app.workers.queue import queue_stats

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class Liveness(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})

    status: Literal["ok"] = "ok"


@router.get(
    "/health",
    response_model=Liveness,
    summary="Liveness",
    operation_id="health",
    responses={
        200: {
            "description": "The process is up",
            "content": {"application/json": {"example": {"status": "ok"}}},
        }
    },
)
async def health() -> Liveness:
    return Liveness()


async def get_probe_session(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AsyncSession:
    """Session used for the DB probe (its own dependency so tests can break only this)."""
    return session


class DeepHealth(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "db": "ok",
                    "redis": "skipped",
                    "laya": "ok",
                    "llm": {"gemini": "ok"},
                    "niches": {"loaded": 5, "errors": []},
                    "queue_depth": 0,
                    "oldest_job_age_s": None,
                }
            ]
        }
    )

    status: Literal["ok", "degraded"]
    db: str
    redis: str
    laya: str
    llm: dict[str, str]
    niches: dict[str, Any]
    queue_depth: int | None
    oldest_job_age_s: float | None


async def _laya_status(request: Request) -> str:
    client = getattr(request.app.state, "laya", None)
    if client is None:
        return "skipped"
    try:
        return str(await client.health())
    except Exception:
        log.warning("laya health failed", exc_info=True)
        return "down"


async def _llm_status() -> dict[str, str]:
    try:
        return {k: str(v) for k, v in (await gateway.ping()).items()}
    except Exception:
        log.warning("llm ping failed", exc_info=True)
        return {"error": "down"}


@router.get(
    "/health/deep",
    response_model=DeepHealth,
    summary="Readiness with dependency checks",
    operation_id="health_deep",
    responses={
        401: {"description": "Missing or invalid API key"},
        503: {"description": "Database is down", "model": DeepHealth},
    },
)
async def health_deep(
    request: Request,
    _: Annotated[Principal, Depends(get_principal)],
    session: Annotated[AsyncSession, Depends(get_probe_session)],
) -> JSONResponse:
    db = "ok"
    depth: int | None = None
    oldest: float | None = None
    try:
        await session.execute(text("select 1"))
        stats = await queue_stats(session)
        depth, oldest = stats.depth, stats.oldest_age_s
    except Exception:
        log.warning("db health failed", exc_info=True)
        db = "down"
    redis = await ping_redis()
    laya = await _laya_status(request)
    llm = await _llm_status()
    registry = get_registry()
    errors = [
        {"file": e.file, "json_pointer": e.json_pointer, "message": e.message}
        for e in registry.errors
    ]
    components = [db, redis, laya, *llm.values()]
    degraded = any(c not in ("ok", "skipped") for c in components) or bool(errors)
    body = DeepHealth(
        status="degraded" if degraded else "ok",
        db=db,
        redis=redis,
        laya=laya,
        llm=llm,
        niches={"loaded": len(registry.all()), "errors": errors},
        queue_depth=depth,
        oldest_job_age_s=oldest,
    )
    return JSONResponse(body.model_dump(), status_code=503 if db == "down" else 200)
