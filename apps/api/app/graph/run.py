"""Run and resume item threads (contract C7, ADR 0003).

Thread id = ``str(item_id)``; every invoke uses ``durability="sync"``; the checkpoint thread is
deleted only when the graph reaches END (never for waiting or crashed threads). The worker and the
resume API both take ``locks.item_lock`` first.

Public API
    run_item(item_id) -> GraphOutcome
    resume_item(item_id, tenant_id, body: DecisionIn) -> GraphOutcome
    unsnooze_item(item_id) -> None
    open_runtime() / close_runtime() / use_runtime(saver)   # lifecycle of the checkpointer pool
"""

import asyncio
import logging
import uuid
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from langgraph.types import Command
from sqlalchemy.exc import NoResultFound

from app.core.config import get_settings
from app.db.session import session_scope
from app.graph import locks, store, store_approval
from app.graph.builder import build_graph
from app.graph.checkpointer import open_checkpointer
from app.graph.errors import (
    InvalidDecision,
    ItemBusy,
    ItemNotFound,
    NotAwaitingApproval,
)
from app.models.enums import ItemStatus
from app.schemas.decision import DecisionIn

log = logging.getLogger(__name__)

__all__ = [
    "GraphOutcome",
    "InvalidDecision",
    "ItemBusy",
    "ItemNotFound",
    "NotAwaitingApproval",
    "close_runtime",
    "open_runtime",
    "resume_item",
    "run_item",
    "unsnooze_item",
    "use_runtime",
]

RUNNABLE = frozenset({ItemStatus.TRIAGED.value, ItemStatus.DECIDING.value})


@dataclass(frozen=True)
class GraphOutcome:
    status: str  # items.status after the invoke
    interrupted: bool  # the thread is waiting for a human


@dataclass
class _Runtime:
    saver: Any
    graph: Any
    loop: asyncio.AbstractEventLoop
    stack: AsyncExitStack | None = None


_runtime: _Runtime | None = None
_init_lock: asyncio.Lock | None = None


async def open_runtime() -> None:
    """Open the checkpointer pool and compile the graph (API lifespan and worker start)."""
    global _runtime, _init_lock
    loop = asyncio.get_running_loop()
    if _runtime is not None and _runtime.loop is loop:
        return
    _init_lock = _init_lock or asyncio.Lock()
    async with _init_lock:
        if _runtime is not None and _runtime.loop is loop:
            return
        stack = AsyncExitStack()
        saver = await stack.enter_async_context(open_checkpointer(get_settings().database_url))
        _runtime = _Runtime(saver, build_graph(saver), loop, stack)


async def close_runtime() -> None:
    global _runtime, _init_lock
    runtime, _runtime, _init_lock = _runtime, None, None
    if runtime is None or runtime.stack is None:
        return
    if runtime.loop is asyncio.get_running_loop():
        await runtime.stack.aclose()


def use_runtime(saver: Any) -> None:
    """Use an already built saver (tests). It is not closed by ``close_runtime``."""
    global _runtime
    _runtime = _Runtime(saver, build_graph(saver), asyncio.get_running_loop())


async def _get_runtime() -> _Runtime:
    runtime = _runtime
    if runtime is None or runtime.loop is not asyncio.get_running_loop():
        await open_runtime()
        runtime = _runtime
    if runtime is None:
        raise RuntimeError("graph runtime failed to open")
    return runtime


def _config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _interrupted(snapshot: Any) -> bool:
    return any(task.interrupts for task in snapshot.tasks)


async def _outcome(runtime: _Runtime, thread_id: str) -> GraphOutcome:
    """Read the result; delete the checkpoint thread only when the graph is at END."""
    snapshot = await runtime.graph.aget_state(_config(thread_id))
    if not snapshot.next:
        await runtime.saver.adelete_thread(thread_id)
    view = await store.load_item_view(thread_id)
    return GraphOutcome(view.status, _interrupted(snapshot))


async def run_item(item_id: uuid.UUID | str) -> GraphOutcome:
    """Start the item's thread, continue a crashed one, or do nothing when it already waits.

    LLM errors (``LLMUnavailable``, ``NoPrivateProvider``) propagate: the item stays ``deciding``
    and the worker retries the job, resuming from the last checkpoint.
    """
    thread_id = str(item_id)
    async with locks.item_lock(thread_id):
        runtime = await _get_runtime()
        snapshot = await runtime.graph.aget_state(_config(thread_id))
        if _interrupted(snapshot):
            return await _outcome(runtime, thread_id)
        if snapshot.next:
            payload: dict[str, Any] | None = None  # continue from the last checkpoint
        else:
            view = await store.load_item_view(thread_id)
            if view.status not in RUNNABLE:
                return GraphOutcome(view.status, False)
            if snapshot.values:  # finished earlier but the thread was not cleaned up
                await runtime.saver.adelete_thread(thread_id)
            payload = {"item_id": thread_id}
        await runtime.graph.ainvoke(payload, _config(thread_id), durability="sync")
        return await _outcome(runtime, thread_id)


async def resume_item(
    item_id: uuid.UUID | str, tenant_id: uuid.UUID | str, body: DecisionIn
) -> GraphOutcome:
    """Apply a human verdict to the waiting thread; ``approve`` runs the actions inline.

    Raises ItemNotFound, NotAwaitingApproval, ItemBusy or InvalidDecision (all validated before
    the thread resumes, because LangGraph replays a failed resume value on the next attempt).
    """
    thread_id = str(item_id)
    async with locks.item_lock(thread_id):
        try:
            view = await store.load_item_view(thread_id)
        except NoResultFound as exc:
            raise ItemNotFound(thread_id) from exc
        if view.tenant_id != str(tenant_id):
            raise ItemNotFound(thread_id)
        if view.status != ItemStatus.AWAITING_APPROVAL.value:
            raise NotAwaitingApproval(f"item is {view.status}")
        _check_option(view.decision, body)
        runtime = await _get_runtime()
        snapshot = await runtime.graph.aget_state(_config(thread_id))
        if not _interrupted(snapshot):
            raise NotAwaitingApproval("item has no pending approval thread")
        resume: Command[Any] = Command(resume=body.model_dump(mode="json"))
        await runtime.graph.ainvoke(resume, _config(thread_id), durability="sync")
        return await _outcome(runtime, thread_id)


def _check_option(decision: dict[str, Any] | None, body: DecisionIn) -> None:
    store_approval.resolve_option(decision, body)  # raises InvalidDecision


async def unsnooze_item(item_id: uuid.UUID | str) -> None:
    """``snoozed -> awaiting_approval`` when the snooze time arrives (the thread still waits)."""
    thread_id = str(item_id)
    async with locks.item_lock(thread_id):
        async with session_scope() as session:
            await store_approval.unsnooze(session, thread_id)
