"""Worker driver and DB read helpers for the acceptance tests (plan A4 helpers.pipeline)."""

import importlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.models import Item
from app.workers.handlers import HANDLERS
from app.workers.run import Worker

SessionFactory = async_sessionmaker[AsyncSession]
PREPARE_NAMES = ("prepare_batch", "prepare", "prepare_jobs")


class SimulatedCrash(BaseException):  # noqa: N818 - BaseException so Worker._process cannot catch it
    """Process death in the middle of the graph."""


def find_prepare() -> Callable[..., Awaitable[None]] | None:
    """The C9 batch hook from ``app.workers.pipeline`` (name not fixed by the plan)."""
    try:
        module = importlib.import_module("app.workers.pipeline")
    except ImportError:
        return None
    for name in PREPARE_NAMES:
        hook = getattr(module, name, None)
        if callable(hook):
            return hook  # type: ignore[no-any-return]
    return None


def build_worker(factory: SessionFactory) -> Worker:
    settings = Settings(worker_batch_size=50)
    prepare = find_prepare()
    extra: dict[str, Any] = {"prepare": prepare} if prepare is not None else {}
    return Worker("acceptance", settings, session_factory=factory, handlers=HANDLERS, **extra)


async def run_worker_until_idle(factory: SessionFactory, max_iters: int = 20) -> int:
    """Run the real worker until a poll claims nothing. Returns jobs processed."""
    worker = build_worker(factory)
    total = 0
    for _ in range(max_iters):
        claimed = await worker.run_once()
        if claimed == 0:
            return total
        total += claimed
    raise AssertionError(f"worker still busy after {max_iters} iterations")


async def load_item(factory: SessionFactory, item_id: str) -> Item:
    async with factory() as session:
        return (await session.scalars(select(Item).where(Item.id == uuid.UUID(item_id)))).one()


async def post_item(
    client: Any, key: str, *, text: str, source_ref: str, hints: dict[str, Any] | None = None
) -> str:
    body: dict[str, Any] = {"source": "manual", "source_ref": source_ref, "payload": {"text": text}}
    if hints:
        body["hints"] = hints
    response = await client.post("/v1/items", json=body, headers=auth(key))
    assert response.status_code == 202, response.text
    return str(response.json()["id"])


def auth(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}
