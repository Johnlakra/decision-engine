"""Tool registry (FR-32)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import BaseModel

from app.tools import registry
from app.tools.registry import ToolResult, registered, run_tool, tool


class PriceArgs(BaseModel):
    crop: str


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    saved = dict(registry._TOOLS)
    registry._CACHE.clear()
    yield
    registry._TOOLS.clear()
    registry._TOOLS.update(saved)
    registry._CACHE.clear()
    registry.set_clock(None)


def _make(name: str = "t.price", *, private_ok: bool = False, ttl_s: int = 60) -> list[int]:
    calls: list[int] = []

    @tool(name, ttl_s=ttl_s, args=PriceArgs, private_ok=private_ok)
    async def fn(args: PriceArgs) -> ToolResult:
        calls.append(1)
        return ToolResult(name=name, data={"crop": args.crop}, as_of="2026-01-01", source="x")

    return calls


def test_duplicate_name_rejected() -> None:
    _make()
    with pytest.raises(ValueError):
        _make()


def test_registered_lists_names() -> None:
    _make()
    assert "t.price" in registered()


async def test_extra_args_ignored() -> None:
    _make()
    res = await run_tool("t.price", {"crop": "wheat", "junk": 1}, sensitivity="public")
    assert res is not None and res.data == {"crop": "wheat"}


async def test_wrong_type_returns_none() -> None:
    calls = _make()
    assert await run_tool("t.price", {"crop": ["a"]}, sensitivity="public") is None
    assert calls == []


async def test_unknown_tool_returns_none() -> None:
    assert await run_tool("nope", {}, sensitivity="public") is None


async def test_cache_hit_and_expiry() -> None:
    now = [1000.0]
    registry.set_clock(lambda: now[0])
    calls = _make(ttl_s=60)
    await run_tool("t.price", {"crop": "w"}, sensitivity="public")
    await run_tool("t.price", {"crop": "w"}, sensitivity="public")
    assert len(calls) == 1
    await run_tool("t.price", {"crop": "other"}, sensitivity="public")
    assert len(calls) == 2
    now[0] += 61
    await run_tool("t.price", {"crop": "w"}, sensitivity="public")
    assert len(calls) == 3


async def test_private_item_skips_non_private_ok_tool() -> None:
    calls = _make()
    assert await run_tool("t.price", {"crop": "w"}, sensitivity="private") is None
    assert calls == []


async def test_private_ok_tool_runs_for_private_item() -> None:
    _make(private_ok=True)
    assert await run_tool("t.price", {"crop": "w"}, sensitivity="private") is not None


async def test_exception_returns_none() -> None:
    @tool("t.boom", ttl_s=1, args=PriceArgs)
    async def boom(args: PriceArgs) -> ToolResult:
        raise RuntimeError("x")

    assert await run_tool("t.boom", {"crop": "w"}, sensitivity="public") is None
