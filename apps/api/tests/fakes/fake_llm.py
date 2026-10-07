"""Test doubles for the LLM gateway.

FakeLLM replaces gateway.complete_json / complete_text (use it from other modules' tests).
FakeProviderCall replaces providers.call (use it to test the gateway itself).
"""

import json
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel

from app.llm import gateway
from app.llm.config import ProviderConfig
from app.llm.errors import LLMUnavailable, NoPrivateProvider, ProviderError
from app.llm.providers import ProviderResponse


class Failure(StrEnum):
    """Simulated failure modes; callers of the gateway see LLMUnavailable for all of them."""

    RATE_LIMIT_429 = "429"
    INVALID_JSON = "invalid_json"
    TIMEOUT = "timeout"


@dataclass
class FakeCall:
    kind: str  # "json" | "text"
    purpose: str
    messages: list[dict[str, Any]]
    sensitivity: str
    language: str
    item_id: str | None
    schema: type[BaseModel] | None = None


class FakeLLM:
    """Scripted gateway: responses are consumed in order per purpose and every call is recorded."""

    def __init__(self) -> None:
        self._scripts: dict[str, deque[Any]] = {}
        self._sticky: set[str] = set()
        self.calls: list[FakeCall] = []
        self.private_available = True

    def script(self, purpose: str, *responses: Any, repeat: bool = False) -> "FakeLLM":
        """Queue BaseModel | dict | str | Failure | Exception. `repeat` keeps the last."""
        self._scripts.setdefault(purpose, deque()).extend(responses)
        if repeat:
            self._sticky.add(purpose)
        return self

    def calls_for(self, purpose: str) -> list[FakeCall]:
        return [c for c in self.calls if c.purpose == purpose]

    def _next(self, purpose: str) -> Any:
        queue = self._scripts.get(purpose)
        if not queue:
            raise LLMUnavailable(f"FakeLLM: no scripted response for purpose {purpose!r}")
        return queue[0] if purpose in self._sticky and len(queue) == 1 else queue.popleft()

    def _record(self, call: FakeCall) -> Any:
        self.calls.append(call)
        if call.sensitivity == "private" and not self.private_available:
            raise NoPrivateProvider("FakeLLM: private provider unavailable")
        item = self._next(call.purpose)
        if isinstance(item, Failure):
            raise LLMUnavailable(f"FakeLLM: simulated {item.value}")
        if isinstance(item, Exception):
            raise item
        return item

    async def complete_json(
        self,
        purpose: str,
        schema: type[BaseModel],
        messages: list[dict[str, Any]],
        *,
        sensitivity: str,
        language: str = "en",
        item_id: str | None = None,
        max_tokens: int | None = None,
    ) -> BaseModel:
        item = self._record(
            FakeCall("json", purpose, messages, sensitivity, language, item_id, schema)
        )
        if isinstance(item, BaseModel):
            return item
        if isinstance(item, str):
            return schema.model_validate_json(item)
        return schema.model_validate(item)

    async def complete_text(
        self,
        purpose: str,
        messages: list[dict[str, Any]],
        *,
        sensitivity: str,
        language: str = "en",
        item_id: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        item = self._record(FakeCall("text", purpose, messages, sensitivity, language, item_id))
        return item if isinstance(item, str) else json.dumps(item)


@pytest.fixture
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeLLM]:
    """Install a FakeLLM on the gateway. Callers must use `gateway.complete_json(...)`."""
    fake = FakeLLM()
    monkeypatch.setattr(gateway, "complete_json", fake.complete_json)
    monkeypatch.setattr(gateway, "complete_text", fake.complete_text)
    yield fake


@dataclass
class RecordedProviderCall:
    provider: str
    messages: list[dict[str, Any]]
    temperature: float
    timeout: float
    max_tokens: int
    response_format: dict[str, Any] | None


@dataclass
class FakeProviderCall:
    """Replacement for providers.call: scripted replies per provider name.

    Items: str (reply text), ProviderResponse, ProviderError or any Exception (raised).
    An unscripted call raises ProviderError("server") so surprises show up as failed attempts.
    """

    scripts: dict[str, deque[Any]] = field(default_factory=dict)
    calls: list[RecordedProviderCall] = field(default_factory=list)

    def script(self, provider: str, *items: Any) -> "FakeProviderCall":
        self.scripts.setdefault(provider, deque()).extend(items)
        return self

    @property
    def called(self) -> list[str]:
        return [c.provider for c in self.calls]

    async def __call__(
        self,
        provider: ProviderConfig,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        timeout: float,  # noqa: ASYNC109 - mirrors providers.call
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
    ) -> ProviderResponse:
        self.calls.append(
            RecordedProviderCall(
                provider.name, messages, temperature, timeout, max_tokens, response_format
            )
        )
        queue = self.scripts.get(provider.name)
        if not queue:
            raise ProviderError("server", "unscripted")
        item = queue.popleft()
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ProviderResponse):
            return item
        return ProviderResponse(
            text=str(item), prompt_tokens=10, completion_tokens=5, model=provider.litellm_model
        )
