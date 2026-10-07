"""Chain selection (FR-60, NFR-06)."""

import pytest

from app.llm.errors import LLMUnavailable
from app.llm.privacy import select_chain
from tests.unit.llm.conftest import make_config

ALL_PUBLIC = {
    "gemini_api_key": "g",
    "groq_api_key": "q",
    "cerebras_api_key": "c",
    "openrouter_api_key": "o",
    "openrouter_model": "openrouter/x/y:free",
}


def names(chain: list) -> list[str]:  # type: ignore[type-arg]
    return [p.name for p in chain]


def test_chain_order_follows_yaml() -> None:
    config = make_config(**ALL_PUBLIC, ollama_url="http://o:11434")
    chain = select_chain("classify", sensitivity="public", language="en", config=config)
    assert names(chain) == ["groq", "gemini", "cerebras", "openrouter", "ollama"]


def test_providers_without_keys_are_skipped() -> None:
    config = make_config(gemini_api_key="g", cerebras_api_key="c")
    chain = select_chain("normalise", sensitivity="public", language="en", config=config)
    assert names(chain) == ["gemini", "cerebras"]


def test_provider_with_key_but_no_model_is_skipped() -> None:
    config = make_config(openrouter_api_key="o", gemini_api_key="g")
    chain = select_chain("summarise", sensitivity="public", language="en", config=config)
    assert names(chain) == ["gemini"]


def test_no_keys_raises_llm_unavailable() -> None:
    with pytest.raises(LLMUnavailable):
        select_chain("decide", sensitivity="public", language="en", config=make_config())


def test_unknown_purpose_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        select_chain("nope", sensitivity="public", language="en", config=make_config(**ALL_PUBLIC))


def test_indic_text_purpose_tries_indic_chain_first_and_dedupes() -> None:
    config = make_config(gemini_api_key="g", groq_api_key="q", sarvam_api_key="s")
    chain = select_chain("summarise", sensitivity="public", language="hi", config=config)
    assert names(chain) == ["gemini", "groq"]  # sarvam has no adapter yet, gemini not repeated


def test_indic_preference_puts_indic_provider_ahead() -> None:
    config = make_config(gemini_api_key="g", groq_api_key="q")
    chain = select_chain("draft", sensitivity="public", language="pa", config=config)
    assert names(chain) == ["gemini", "groq"]
    plain = select_chain("draft", sensitivity="public", language="en", config=config)
    assert names(plain) == ["gemini", "groq"]


def test_indic_language_does_not_change_non_text_purposes() -> None:
    config = make_config(gemini_api_key="g", groq_api_key="q")
    chain = select_chain("classify", sensitivity="public", language="hi", config=config)
    assert names(chain) == ["groq", "gemini"]


def test_env_overrides_model_and_budget() -> None:
    config = make_config(
        gemini_api_key="g", gemini_model="gemini/gemini-3.5-flash-lite", gemini_rpd=42
    )
    gemini = config.providers["gemini"]
    assert gemini.litellm_model == "gemini/gemini-3.5-flash-lite"
    assert gemini.rpd == 42


def test_api_key_never_appears_in_repr() -> None:
    config = make_config(gemini_api_key="super-secret-key")
    assert "super-secret-key" not in repr(config.providers["gemini"])
