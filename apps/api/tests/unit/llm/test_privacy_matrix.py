"""A private item never reaches a provider without private_ok, for every purpose (NFR-06, FR-12)."""

import pytest
from pydantic import BaseModel

from app.llm import gateway
from app.llm.errors import NoPrivateProvider
from tests.unit.llm.conftest import LLMEnv

KEYS = {
    "gemini_api_key": "g",
    "groq_api_key": "q",
    "cerebras_api_key": "c",
    "openrouter_api_key": "o",
    "openrouter_model": "openrouter/x/y:free",
    "sarvam_api_key": "s",
    "openai_api_key": "k",
    "openai_model": "gpt-x",
    "openai_private_ok": False,
}
FREE_AND_PAID = ("gemini", "groq", "cerebras", "openrouter", "sarvam", "openai")
PURPOSES = ("normalise", "classify", "decide", "summarise", "draft")
MSGS = [{"role": "user", "content": "PRIVATE-BODY"}]


class Out(BaseModel):
    ok: bool


@pytest.mark.parametrize("purpose", PURPOSES)
@pytest.mark.parametrize("language", ["en", "hi", "pa"])
async def test_no_private_provider_means_zero_provider_calls(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch, purpose: str, language: str
) -> None:
    llm_env.configure(monkeypatch, **KEYS)
    for name in FREE_AND_PAID:
        llm_env.provider_calls.script(name, "LEAK", '{"ok": true}')
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_text(purpose, MSGS, sensitivity="private", language=language)
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_json(purpose, Out, MSGS, sensitivity="private", language=language)
    assert llm_env.provider_calls.called == []


@pytest.mark.parametrize("purpose", PURPOSES)
async def test_private_with_ollama_only_ever_calls_ollama(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch, purpose: str
) -> None:
    llm_env.configure(monkeypatch, **KEYS, ollama_url="http://ollama:11434")
    for name in FREE_AND_PAID:
        llm_env.provider_calls.script(name, "LEAK")
    llm_env.provider_calls.script("ollama", '{"ok": true}', "plain")
    await gateway.complete_json(purpose, Out, MSGS, sensitivity="private")
    await gateway.complete_text(purpose, MSGS, sensitivity="private")
    assert set(llm_env.provider_calls.called) == {"ollama"}


async def test_openai_with_private_ok_is_allowed_for_private(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm_env.configure(monkeypatch, **{**KEYS, "openai_private_ok": True})
    llm_env.provider_calls.script("openai", "paid-ok")
    assert await gateway.complete_text("decide", MSGS, sensitivity="private") == "paid-ok"
    assert llm_env.provider_calls.called == ["openai"]
