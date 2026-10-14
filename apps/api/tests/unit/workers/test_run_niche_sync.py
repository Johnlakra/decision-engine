"""Worker syncs niche overrides once per non-empty batch, before prepare (ADR 0009)."""

from types import TracebackType
from typing import Any

import pytest

from app.core.config import get_settings
from app.workers import run as run_mod
from app.workers.run import Worker


class _Session:
    async def __aenter__(self) -> "_Session":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None


def _factory() -> _Session:
    return _Session()


async def _run(monkeypatch: pytest.MonkeyPatch, jobs: list[Any]) -> list[str]:
    calls: list[str] = []

    async def claim(*_: Any, **__: Any) -> list[Any]:
        return jobs

    async def sync(_session: Any) -> bool:
        calls.append("sync")
        return False

    async def prepare(*_: Any) -> None:
        calls.append("prepare")

    monkeypatch.setattr(run_mod.queue, "claim", claim)
    monkeypatch.setattr(run_mod, "sync_registry", sync)
    worker = Worker(
        "w",
        get_settings(),
        session_factory=_factory,
        handlers={},
        prepare=prepare,  # type: ignore[arg-type]
    )
    worker.stop()  # release instead of processing: only the claim path is under test
    monkeypatch.setattr(run_mod.queue, "release", claim)
    await worker.run_once()
    return calls


async def test_sync_runs_once_before_prepare_for_a_non_empty_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert await _run(monkeypatch, [object(), object()]) == ["sync", "prepare"]


async def test_no_sync_when_nothing_was_claimed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert await _run(monkeypatch, []) == []
