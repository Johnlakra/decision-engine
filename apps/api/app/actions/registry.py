"""Action registry and idempotent runner (C4, FR-40, FR-41, NFR-07).

Actions never write items.status; the graph's act node owns status.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.models import ActionLog
from app.models.enums import ActionStatus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionContext:
    session: AsyncSession
    tenant_id: uuid.UUID
    item_id: uuid.UUID
    option_id: str | None = None
    action_log_id: uuid.UUID | None = None  # set by run_action (additive to C4)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


ActionFn = Callable[[ActionContext, Any], Awaitable[ActionResult]]


@dataclass(frozen=True)
class ActionDef:
    name: str
    fn: ActionFn
    reversible: bool
    params: type[BaseModel]


_ACTIONS: dict[str, ActionDef] = {}


def action(
    name: str, *, reversible: bool = False, params: type[BaseModel]
) -> Callable[[ActionFn], ActionFn]:
    def deco(fn: ActionFn) -> ActionFn:
        if name in _ACTIONS:
            raise ValueError(f"action already registered: {name}")
        _ACTIONS[name] = ActionDef(name, fn, reversible, params)
        return fn

    return deco


def registered() -> frozenset[str]:
    return frozenset(_ACTIONS)


def names() -> list[str]:
    return sorted(_ACTIONS)


def get(name: str) -> ActionDef:
    return _ACTIONS[name]


def _canonical(params: Any) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def idem_key(item_id: uuid.UUID | str, name: str, params: Any) -> str:
    return hashlib.sha256(f"{item_id}|{name}|{_canonical(params)}".encode()).hexdigest()


def _stored(row: ActionLog) -> ActionResult:
    stored = row.result or {}
    if row.status == ActionStatus.DONE.value:
        return ActionResult(True, stored.get("data", {}), None)
    if row.status == ActionStatus.PENDING.value:
        return ActionResult(False, {}, "in_progress")
    return ActionResult(False, stored.get("data", {}), stored.get("error") or "failed")


def _result_json(result: ActionResult) -> dict[str, Any]:
    return {"ok": result.ok, "data": result.data, "error": result.error}


async def _execute(ctx: ActionContext, spec: ActionDef, params: BaseModel) -> ActionResult:
    try:
        async with ctx.session.begin_nested():
            return await spec.fn(ctx, params)
    except Exception as exc:  # recorded, never raised (C4)
        log.warning(
            "action failed name=%s item=%s err=%s", spec.name, ctx.item_id, type(exc).__name__
        )
        return ActionResult(False, {}, type(exc).__name__)


async def run_action(ctx: ActionContext, name: str, params: dict[str, Any]) -> ActionResult:
    spec = _ACTIONS.get(name)
    if spec is None:
        return ActionResult(False, {}, "unknown_action")
    raw = json.loads(_canonical(params if isinstance(params, dict) else {}))
    validated: BaseModel | None = None
    try:
        validated = spec.params.model_validate(raw)
        stored_params = validated.model_dump(mode="json")
        failure = None
    except ValidationError:
        stored_params, failure = raw, ActionResult(False, {}, "invalid_params")
    key = idem_key(ctx.item_id, name, stored_params)
    log_id = new_id()
    inserted = await ctx.session.execute(
        insert(ActionLog)
        .values(
            id=log_id,
            tenant_id=ctx.tenant_id,
            item_id=ctx.item_id,
            action=name,
            params=stored_params,
            idem_key=key,
            status=ActionStatus.PENDING.value,
            reversible=spec.reversible,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "idem_key"])
        .returning(ActionLog.id)
    )
    if inserted.scalar_one_or_none() is None:
        existing = await ctx.session.execute(
            select(ActionLog).where(ActionLog.tenant_id == ctx.tenant_id, ActionLog.idem_key == key)
        )
        return _stored(existing.scalar_one())
    if failure is None and validated is not None:
        result = await _execute(replace(ctx, action_log_id=log_id), spec, validated)
    else:
        result = failure or ActionResult(False, {}, "invalid_params")
    status = ActionStatus.DONE if result.ok else ActionStatus.FAILED
    await ctx.session.execute(
        update(ActionLog)
        .where(ActionLog.id == log_id)
        .values(status=status.value, result=_result_json(result))
    )
    return result
