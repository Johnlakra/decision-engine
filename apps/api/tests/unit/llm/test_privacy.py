"""A private call can never reach a free tier (CLAUDE.md privacy rule, FR-61, NFR-04)."""

import pytest

from app.llm.config import LLMConfig
from app.llm.errors import LLMUnavailable, NoPrivateProvider
from app.llm.privacy import NEVER_PRIVATE, assert_private_safe, select_chain
from tests.unit.llm.conftest import make_config

KEYS = {
    "gemini_api_key": "g",
    "groq_api_key": "q",
    "cerebras_api_key": "c",
    "openrouter_api_key": "o",
    "openrouter_model": "openrouter/x/y:free",
    "sarvam_api_key": "s",
}


def private_first(config: LLMConfig, *, force_flag: bool) -> LLMConfig:
    """Worst case: free tiers listed first in the private chain, even flagged private_ok."""
    providers = dict(config.providers)
    if force_flag:
        providers = {n: p.model_copy(update={"private_ok": True}) for n, p in providers.items()}
    chains = dict(config.chains)
    chains["private"] = ("gemini", "groq", "cerebras", "openrouter", "sarvam", "ollama", "openai")
    return config.model_copy(update={"providers": providers, "chains": chains})


@pytest.mark.parametrize("force_flag", [False, True])
def test_private_never_selects_free_tiers_even_when_first(force_flag: bool) -> None:
    config = private_first(make_config(**KEYS, ollama_url="http://o:11434"), force_flag=force_flag)
    chain = select_chain("classify", sensitivity="private", language="en", config=config)
    assert [p.name for p in chain] == ["ollama"]
    assert not NEVER_PRIVATE & {p.name for p in chain}


@pytest.mark.parametrize("force_flag", [False, True])
def test_private_with_only_free_tiers_raises_no_private_provider(force_flag: bool) -> None:
    config = private_first(make_config(**KEYS), force_flag=force_flag)
    with pytest.raises(NoPrivateProvider):
        select_chain("classify", sensitivity="private", language="en", config=config)


def test_default_private_chain_without_ollama_raises() -> None:
    with pytest.raises(NoPrivateProvider):
        select_chain("decide", sensitivity="private", language="en", config=make_config(**KEYS))


def test_no_private_provider_is_an_llm_unavailable() -> None:
    assert issubclass(NoPrivateProvider, LLMUnavailable)


def test_openai_is_private_only_when_terms_allow() -> None:
    base = {**KEYS, "openai_api_key": "k", "openai_model": "openai/gpt-x"}
    closed = make_config(**base, ollama_url="http://o")
    names = [p.name for p in select_chain("decide", sensitivity="private", config=closed)]
    assert names == ["ollama"]
    opened = make_config(**base, ollama_url="http://o", openai_private_ok=True)
    names = [p.name for p in select_chain("decide", sensitivity="private", config=opened)]
    assert names == ["ollama", "openai"]


def test_private_chain_ignores_language_and_purpose_lists() -> None:
    config = make_config(**KEYS, ollama_url="http://o")
    chain = select_chain("summarise", sensitivity="private", language="hi", config=config)
    assert [p.name for p in chain] == ["ollama"]


@pytest.mark.parametrize("name", sorted(NEVER_PRIVATE))
def test_assert_private_safe_rejects_every_free_tier(name: str) -> None:
    config = make_config(**KEYS)
    provider = config.providers[name].model_copy(update={"private_ok": True})
    with pytest.raises(NoPrivateProvider):
        assert_private_safe([provider])
