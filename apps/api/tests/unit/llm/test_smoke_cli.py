"""python -m app.llm.smoke edge paths: unknown provider, mixed results, no key in output (A6)."""

import pytest

from app.llm import smoke
from app.llm.errors import ProviderError
from tests.unit.llm.conftest import LLMEnv

SECRET = "sk-super-secret-value"


@pytest.fixture
def env(llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch) -> LLMEnv:
    config = llm_env.configure(monkeypatch, gemini_api_key=SECRET, groq_api_key=SECRET + "2")
    monkeypatch.setattr(smoke, "load_config", lambda: config)
    return llm_env


def test_unknown_provider_exits_1(env: LLMEnv, capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main(["--provider", "nope"]) == 1
    assert "unknown provider" in capsys.readouterr().out


def test_all_configured_providers_ok_exits_0_and_prints_no_key(
    env: LLMEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    good = '{"answer": "yes", "reason": "rayleigh"}'
    env.provider_calls.script("gemini", good)
    env.provider_calls.script("groq", good)
    assert smoke.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("OK ") == 2 and SECRET not in out


def test_one_failing_provider_makes_exit_1_even_if_another_is_ok(
    env: LLMEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    env.provider_calls.script("gemini", '{"answer": "yes", "reason": "r"}')
    env.provider_calls.script("groq", ProviderError("auth"))
    assert smoke.main([]) == 1
    out = capsys.readouterr().out
    assert "FAIL groq" in out and SECRET not in out


def test_skipped_message_names_the_env_var_not_its_value(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = llm_env.configure(monkeypatch, groq_api_key=SECRET)
    monkeypatch.setattr(smoke, "load_config", lambda: config)
    assert smoke.main(["--provider", "gemini"]) == 2
    out = capsys.readouterr().out
    assert "GEMINI_API_KEY" in out and SECRET not in out
