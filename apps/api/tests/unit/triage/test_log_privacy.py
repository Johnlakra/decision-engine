"""Triage logs never carry exception messages or tracebacks (NFR-07, FR-20)."""

import logging
import uuid
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.triage import service
from tests.fakes.fake_llm import FakeLLM
from tests.unit.triage import test_service as ts
from tests.unit.triage.test_service import item, llm_reply, run

env = ts.env  # reuse the triage service fixture
SENTINEL = "SENTINEL-SECRET-BODY-123"


class _Model(BaseModel):
    n: int


def _validation_error() -> ValidationError:
    try:
        _Model.model_validate({"n": SENTINEL})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected ValidationError")


def _own(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name.startswith("app.triage")]


def _dump(caplog: pytest.LogCaptureFixture) -> str:
    parts: list[str] = []
    for r in _own(caplog):
        parts.append(f"{r.getMessage()} {r.__dict__}")
        if r.exc_info:
            parts.append(repr(r.exc_info[1]))
        parts.append(str(r.exc_text))
    return " ".join(parts)


def _assert_clean(caplog: pytest.LogCaptureFixture, item_id: uuid.UUID) -> None:
    text = _dump(caplog)
    assert SENTINEL not in text
    assert all(r.exc_info is None for r in _own(caplog))
    assert _own(caplog)
    assert str(item_id) in text
    assert "ValidationError" in text


class _RaisingClient:
    async def batch(self, *_: Any, **__: Any) -> Any:
        raise _validation_error()


async def test_laya_client_exception_not_logged(
    env: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    fake_llm: FakeLLM,
) -> None:
    env["laya"] = _RaisingClient()
    fake_llm.script("classify", llm_reply())
    caplog.set_level(logging.DEBUG)
    it = item()

    await run([it])
    assert SENTINEL not in _dump(caplog)
    assert "ValidationError" in _dump(caplog)
    assert all(r.exc_info is None for r in _own(caplog))


async def test_fallback_exception_not_logged(
    env: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_: Any, **__: Any) -> Any:
        raise _validation_error()

    monkeypatch.setattr(service, "classify", boom)
    caplog.set_level(logging.DEBUG)
    it = item()
    await run([it])
    _assert_clean(caplog, it.id)


async def test_finalise_exception_not_logged(
    env: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = service._finalise
    calls = {"n": 0}

    def flaky(work: Any, registry: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _validation_error()
        return real(work, registry)

    monkeypatch.setattr(service, "_finalise", flaky)
    caplog.set_level(logging.DEBUG)
    it = item()
    await run([it])
    _assert_clean(caplog, it.id)


async def test_stage_exception_not_logged(
    env: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(*_: Any, **__: Any) -> Any:
        raise _validation_error()

    monkeypatch.setattr(service, "_phase_core", boom)
    caplog.set_level(logging.DEBUG)
    it = item()
    await run([it])
    _assert_clean(caplog, it.id)
