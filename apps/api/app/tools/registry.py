"""Tool registry with in-process TTL cache (FR-32).

A tool is an async function taking a validated args model and returning a ToolResult.
Failures never raise out of ``run_tool``: they are logged and yield ``None``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

Sensitivity = Literal["public", "private"]


class ToolResult(BaseModel):
    name: str
    data: dict[str, Any]
    as_of: str | None = None
    source: str | None = None


ToolFn = Callable[[Any], Awaitable[ToolResult]]


@dataclass(frozen=True)
class _Tool:
    name: str
    fn: ToolFn
    ttl_s: int
    args: type[BaseModel]
    private_ok: bool


_TOOLS: dict[str, _Tool] = {}
_CACHE: dict[str, tuple[float, ToolResult]] = {}
_clock: Callable[[], float] = time.monotonic


def set_clock(clock: Callable[[], float] | None) -> None:
    """Inject a clock for tests; ``None`` restores the default."""
    global _clock
    _clock = clock or time.monotonic


def tool(
    name: str, *, ttl_s: int, args: type[BaseModel], private_ok: bool = False
) -> Callable[[ToolFn], ToolFn]:
    def deco(fn: ToolFn) -> ToolFn:
        if name in _TOOLS:
            raise ValueError(f"tool already registered: {name}")
        _TOOLS[name] = _Tool(name, fn, ttl_s, args, private_ok)
        return fn

    return deco


def registered() -> frozenset[str]:
    return frozenset(_TOOLS)


def _cache_key(name: str, args: BaseModel) -> str:
    canonical = json.dumps(args.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{name}|{canonical}".encode()).hexdigest()


async def run_tool(
    name: str, extracted: dict[str, Any], *, sensitivity: Sensitivity
) -> ToolResult | None:
    spec = _TOOLS.get(name)
    if spec is None:
        log.warning("tool unknown: %s", name)
        return None
    if sensitivity == "private" and not spec.private_ok:
        log.info("tool skipped for private item: %s", name)
        return None
    try:
        args = spec.args.model_validate(extracted)
    except ValidationError:
        log.warning("tool args invalid: %s", name)
        return None
    key = _cache_key(name, args)
    now = _clock()
    hit = _CACHE.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    try:
        result = await spec.fn(args)
    except Exception:
        log.warning("tool failed: %s", name, exc_info=True)
        return None
    _CACHE[key] = (now + spec.ttl_s, result)
    return result
