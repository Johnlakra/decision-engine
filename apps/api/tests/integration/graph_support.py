"""Shared setup for graph/API integration tests: real Postgres, real checkpointer, fake LLM."""

import importlib
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import APIRouter, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.niches.registry as reg_mod
from app.api.deps import get_rate_limiter
from app.core.errors import install_problem_handlers
from app.core.ids import new_id
from app.graph import run
from app.models import Item, Job, Tenant, WebhookSubscription
from app.models.enums import JobKind
from app.security.rate_limit import MemoryRateLimiter
from tests.unit.graph.test_builder import fresh_registry
from tests.unit.graph.world import DECISION_OUT, TRIAGE

SessionFactory = async_sessionmaker[AsyncSession]
ALL_EVENTS = ["item.triaged", "decision.ready", "decision.made", "action.done"]


@pytest.fixture
def real_niches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(reg_mod, "_registry", fresh_registry())
    yield


@pytest_asyncio.fixture
async def runtime(committed_db: SessionFactory, real_niches: None) -> AsyncIterator[None]:
    """The real AsyncPostgresSaver pool for this test's event loop."""
    await run.open_runtime()
    yield
    await run.close_runtime()


async def make_item(
    factory: SessionFactory,
    tenant: Tenant,
    *,
    subscribe: bool = True,
    status: str = "triaged",
    niche: str = "generic",
    sensitivity: str = "public",
    risk: str = "normal",
    triage: dict[str, Any] | None = None,
) -> uuid.UUID:
    item_id = new_id()
    async with factory() as session:
        session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                source="manual",
                source_ref=str(item_id),
                raw={},
                status=status,
                niche=niche,
                sensitivity=sensitivity,
                risk=risk,
                language="en",
                content={"title": "Pay the water bill", "body": "Due Friday, Rs 400"},
                triage=triage or TRIAGE,
            )
        )
        if subscribe:
            session.add(
                WebhookSubscription(
                    id=new_id(),
                    tenant_id=tenant.id,
                    url="https://example.com/hook",
                    events=ALL_EVENTS,
                    secret_enc="x",
                    enabled=True,
                )
            )
        await session.commit()
    return item_id


async def load(factory: SessionFactory, item_id: uuid.UUID) -> Item:
    async with factory() as session:
        return (await session.scalars(select(Item).where(Item.id == item_id))).one()


async def event_names(factory: SessionFactory) -> list[str]:
    async with factory() as session:
        rows = await session.scalars(select(Job).where(Job.kind == JobKind.WEBHOOK.value))
        return sorted(job.payload["event"] for job in rows)


async def count_rows(factory: SessionFactory, model: Any) -> int:
    async with factory() as session:
        return len((await session.scalars(select(model))).all())


__all__ = ["DECISION_OUT"]


@pytest_asyncio.fixture
async def mini_client(
    committed_db: SessionFactory, real_niches: None
) -> AsyncIterator[httpx.AsyncClient]:
    """An ASGI client on an app that mounts only the routers under test (wiring is step W)."""
    app = FastAPI()
    install_problem_handlers(app)
    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    v1 = APIRouter(prefix="/v1")
    for module in ("app.api.v1.decisions", "app.api.v1.decide"):
        try:
            v1.include_router(importlib.import_module(module).router)
        except ImportError:
            continue
    app.include_router(v1)
    async with run_lifespan_runtime():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            yield client


@asynccontextmanager
async def run_lifespan_runtime() -> AsyncIterator[None]:
    await run.open_runtime()
    try:
        yield
    finally:
        await run.close_runtime()


def bearer(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}
