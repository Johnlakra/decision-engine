"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.api import v1 as v1_api
from app.core.config import get_settings
from app.core.errors import install_problem_handlers
from app.core.logging import configure_logging
from app.niches.registry import get_registry
from app.triage.laya_client import HttpLayaClient

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    registry = get_registry()  # raises MissingGenericNicheError: refuse to boot without generic
    log.info("niches loaded: %s", ",".join(n.name for n in registry.all()))
    laya = HttpLayaClient.from_settings(settings)
    app.state.laya = laya
    try:
        yield
    finally:
        if laya is not None:
            await laya.aclose()


def create_app() -> FastAPI:
    """Build the app (uvicorn ``--factory`` target)."""
    app = FastAPI(title="Decision Engine API", version="0.1.0", lifespan=lifespan)
    app.state.laya = None
    install_problem_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_api.router)
    return app


app = create_app()
