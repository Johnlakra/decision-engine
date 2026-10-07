"""Fixtures for the gateway tests: fake providers, fake budget store, recorded usage rows."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.core.config import Settings
from app.llm import gateway, providers, usage
from app.llm.budgets import InMemoryBudgetStore, set_budget_store
from app.llm.config import LLMConfig, ProviderConfig, load_config
from tests.fakes.fake_llm import FakeLLM, FakeProviderCall, fake_llm

__all__ = ["fake_llm", "FakeLLM"]

NO_KEYS: dict[str, Any] = {
    "gemini_api_key": "",
    "groq_api_key": "",
    "cerebras_api_key": "",
    "openrouter_api_key": "",
    "openrouter_model": "",
    "sarvam_api_key": "",
    "ollama_url": "",
    "openai_api_key": "",
    "openai_model": "",
    "openai_private_ok": False,
}


def make_config(**overrides: Any) -> LLMConfig:
    """Config from explicit values only (neither the shell env nor .env leaks in)."""
    return load_config(Settings(_env_file=None, **{**NO_KEYS, **overrides}))  # type: ignore[arg-type]


@dataclass
class LLMEnv:
    provider_calls: FakeProviderCall
    store: InMemoryBudgetStore
    usage_rows: list[dict[str, Any]] = field(default_factory=list)
    now: datetime | None = None

    def configure(self, monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> LLMConfig:
        config = make_config(**overrides)
        monkeypatch.setattr(gateway, "load_config", lambda: config)
        return config

    def provider(self, config: LLMConfig, name: str) -> ProviderConfig:
        return config.providers[name]


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[LLMEnv]:
    fake_call = FakeProviderCall()
    store = InMemoryBudgetStore()
    env = LLMEnv(provider_calls=fake_call, store=store)

    async def record(_factory: Any, **row: Any) -> None:
        row["provider"] = row["provider"].name
        env.usage_rows.append(row)

    monkeypatch.setattr(providers, "call", fake_call)
    monkeypatch.setattr(usage, "record_usage", record)
    set_budget_store(store)
    gateway.reset_ping_cache()
    yield env
    set_budget_store(None)
    gateway.reset_ping_cache()
