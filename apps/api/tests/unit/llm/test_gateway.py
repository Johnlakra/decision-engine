"""Gateway behaviour with providers.call replaced (FR-12, FR-60, FR-61, FR-62, NFR-04, NFR-06)."""

import logging
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from app.llm import gateway
from app.llm.budgets import seconds_until_utc_midnight
from app.llm.config import load_config
from app.llm.errors import LLMUnavailable, NoPrivateProvider, ProviderError
from tests.unit.llm.conftest import LLMEnv

KEYS = {
    "gemini_api_key": "g",
    "groq_api_key": "q",
    "cerebras_api_key": "c",
    "openrouter_api_key": "o",
    "openrouter_model": "openrouter/x/y:free",
}
Msgs = [{"role": "user", "content": "SECRET-BODY-123"}]


class Answer(BaseModel):
    ok: bool


@pytest.fixture
def env(llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch) -> LLMEnv:
    llm_env.configure(monkeypatch, **KEYS, ollama_url="http://ollama:11434")
    return llm_env


async def test_falls_through_to_next_provider_and_marks_cooldown(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", ProviderError("rate_limit"))
    env.provider_calls.script("groq", "hello")
    result = await gateway.complete_text("decide", Msgs, sensitivity="public")
    assert result == "hello"
    assert env.provider_calls.called == ["gemini", "groq"]
    assert await env.store.is_cooling("gemini")


async def test_cooled_down_provider_is_skipped_next_time(env: LLMEnv) -> None:
    await env.store.cool_down("gemini", 60)
    env.provider_calls.script("groq", "hi")
    await gateway.complete_text("decide", Msgs, sensitivity="public")
    assert env.provider_calls.called == ["groq"]


async def test_per_day_429_cools_down_until_utc_midnight(
    env: LLMEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    noon = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(gateway, "utcnow", lambda: noon)
    seen: list[int] = []
    original = env.store.cool_down

    async def spy(provider: str, seconds: int) -> None:
        seen.append(seconds)
        await original(provider, seconds)

    monkeypatch.setattr(env.store, "cool_down", spy)
    env.provider_calls.script("gemini", ProviderError("rate_limit_day"))
    env.provider_calls.script("groq", "x")
    await gateway.complete_text("decide", Msgs, sensitivity="public")
    assert seen == [seconds_until_utc_midnight(noon)] == [43200]


async def test_budget_exhaustion_skips_provider(env: LLMEnv) -> None:
    for _ in range(500):  # gemini rpd
        await env.store.incr("gemini")
    env.provider_calls.script("gemini", "never")
    env.provider_calls.script("groq", "ok")
    assert await gateway.complete_text("decide", Msgs, sensitivity="public") == "ok"
    assert env.provider_calls.called == ["groq"]


async def test_every_attempt_counts_against_budget(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", ProviderError("server"))
    env.provider_calls.script("groq", "ok")
    await gateway.complete_text("decide", Msgs, sensitivity="public")
    assert await env.store.count("gemini") == 1
    assert await env.store.count("groq") == 1


async def test_all_failing_raises_llm_unavailable(env: LLMEnv) -> None:
    with pytest.raises(LLMUnavailable) as info:
        await gateway.complete_text("summarise", Msgs, sensitivity="public")
    assert not isinstance(info.value, NoPrivateProvider)


async def test_timeout_and_options_passed_to_provider(env: LLMEnv) -> None:
    env.provider_calls.script("groq", "x")
    await gateway.complete_text("classify", Msgs, sensitivity="public")
    call = env.provider_calls.calls[0]
    assert (call.provider, call.timeout, call.temperature) == ("groq", 45.0, 0.0)
    env.provider_calls.script("gemini", "x")
    await gateway.complete_text("decide", Msgs, sensitivity="public", max_tokens=77)
    assert (env.provider_calls.calls[1].temperature, env.provider_calls.calls[1].max_tokens) == (
        0.2,
        77,
    )


async def test_empty_text_reply_tries_next_provider(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", "   ")
    env.provider_calls.script("groq", "real")
    assert await gateway.complete_text("decide", Msgs, sensitivity="public") == "real"


# --- privacy (CLAUDE.md, FR-61, NFR-04) ---


async def test_private_call_only_reaches_ollama(env: LLMEnv) -> None:
    for name in ("gemini", "groq", "cerebras", "openrouter"):
        env.provider_calls.script(name, "LEAK")
    env.provider_calls.script("ollama", "local")
    assert await gateway.complete_text("classify", Msgs, sensitivity="private") == "local"
    assert env.provider_calls.called == ["ollama"]


async def test_private_failure_raises_no_private_provider_without_touching_free_tiers(
    env: LLMEnv,
) -> None:
    for name in ("gemini", "groq", "cerebras", "openrouter"):
        env.provider_calls.script(name, "LEAK")
    env.provider_calls.script("ollama", ProviderError("server"))
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_json("classify", Answer, Msgs, sensitivity="private")
    assert set(env.provider_calls.called) == {"ollama"}


async def test_private_without_ollama_raises_before_any_call(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm_env.configure(monkeypatch, **KEYS)
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_text("decide", Msgs, sensitivity="private")
    assert llm_env.provider_calls.called == []


async def test_private_json_reaches_only_private_even_after_repair(env: LLMEnv) -> None:
    env.provider_calls.script("ollama", "not json", "still not")
    with pytest.raises(NoPrivateProvider):
        await gateway.complete_json("decide", Answer, Msgs, sensitivity="private")
    assert env.provider_calls.called == ["ollama", "ollama"]


# --- usage log (FR-62) ---


async def test_every_attempt_writes_one_usage_row(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", ProviderError("rate_limit"))
    env.provider_calls.script("groq", "ok")
    await gateway.complete_text("decide", Msgs, sensitivity="public", item_id="abc")
    rows = env.usage_rows
    assert [(r["provider"], r["ok"], r["error_code"]) for r in rows] == [
        ("gemini", False, "rate_limit"),
        ("groq", True, None),
    ]
    assert rows[1]["prompt_tokens"] == 10 and rows[1]["completion_tokens"] == 5
    assert all(r["purpose"] == "decide" and r["item_id"] == "abc" for r in rows)


async def test_logs_never_contain_message_bodies(
    env: LLMEnv, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    env.provider_calls.script("gemini", ProviderError("server"))
    env.provider_calls.script("groq", "reply-body-xyz")
    await gateway.complete_text("decide", Msgs, sensitivity="public", item_id="i1")
    text = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
    assert "SECRET-BODY-123" not in text and "reply-body-xyz" not in text
    assert "i1" in text


# --- ping ---


async def test_ping_statuses_and_cache(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", "pong")
    first = await gateway.ping("gemini")
    second = await gateway.ping("gemini")
    assert first == second == {"gemini": "ok"}
    assert env.provider_calls.called == ["gemini"]  # second call served from cache


async def test_ping_cache_expires_after_five_minutes(
    env: LLMEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [1000.0]
    monkeypatch.setattr(gateway, "_ping_clock", lambda: now[0])
    env.provider_calls.script("gemini", "pong", "pong")
    await gateway.ping("gemini")
    now[0] += 299
    await gateway.ping("gemini")
    assert env.provider_calls.called == ["gemini"]
    now[0] += 2
    await gateway.ping("gemini")
    assert env.provider_calls.called == ["gemini", "gemini"]


async def test_ping_reports_down_skipped_cooldown(env: LLMEnv) -> None:
    await env.store.cool_down("groq", 60)
    env.provider_calls.script("gemini", ProviderError("server"))
    result = await gateway.ping()
    assert result["gemini"] == "down"
    assert result["groq"] == "cooldown"
    assert result["sarvam"] == "skipped"
    assert result["openai"] == "skipped"


async def test_ping_skips_provider_over_80_percent_of_budget(env: LLMEnv) -> None:
    for _ in range(400):  # 80% of 500
        await env.store.incr("gemini")
    result = await gateway.ping("gemini")
    assert result == {"gemini": "over_budget"}
    assert env.provider_calls.called == []


async def test_ping_logs_usage_with_ping_purpose(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", "pong")
    await gateway.ping("gemini")
    assert [r["purpose"] for r in env.usage_rows] == ["ping"]


# --- exception classification (providers.classify_exception) ---


class _Err(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("exc", "kind"),
    [
        (_Err("Rate limit reached on requests per minute", 429), "rate_limit"),
        (
            _Err("quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier", 429),
            "rate_limit_day",
        ),
        (_Err("Rate limit reached on tokens per day (TPD)", 429), "rate_limit_day"),
        (_Err("insufficient credits", 402), "rate_limit_day"),
        (TimeoutError(), "timeout"),
        (_Err("slow", 408), "timeout"),
        (_Err("bad key", 401), "auth"),
        (_Err("bad model", 404), "bad_request"),
        (_Err("overloaded", 503), "server"),
        (ValueError("boom"), "other"),
    ],
)
def test_classify_exception(exc: Exception, kind: str) -> None:
    from app.llm.providers import classify_exception

    assert classify_exception(exc).kind == kind


def test_classified_error_never_carries_the_message() -> None:
    from app.llm.providers import classify_exception

    assert "SECRET" not in str(classify_exception(_Err("SECRET prompt text", 500)))


async def test_unexpected_exception_from_call_is_treated_as_failed_attempt(env: LLMEnv) -> None:
    env.provider_calls.script("gemini", RuntimeError("kaboom"))
    env.provider_calls.script("groq", "fine")
    assert await gateway.complete_text("decide", Msgs, sensitivity="public") == "fine"


# --- smoke (python -m app.llm.smoke) ---


def test_smoke_skipped_without_key(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.llm import smoke

    config = llm_env.configure(monkeypatch)
    monkeypatch.setattr(smoke, "load_config", lambda: config)
    assert smoke.main(["--provider", "gemini"]) == 2
    assert capsys.readouterr().out.strip() == "SKIPPED: GEMINI_API_KEY not set"
    assert smoke.main([]) == 2


def test_smoke_ok_and_fail_never_print_keys(
    llm_env: LLMEnv, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.llm import smoke

    config = llm_env.configure(monkeypatch, gemini_api_key="sk-very-secret")
    monkeypatch.setattr(smoke, "load_config", lambda: config)
    llm_env.provider_calls.script("gemini", '{"answer": "yes", "reason": "light scattering"}')
    assert smoke.main(["--provider", "gemini"]) == 0
    out = capsys.readouterr().out
    assert "light scattering" in out and "sk-very-secret" not in out
    llm_env.provider_calls.script("gemini", ProviderError("auth"))
    assert smoke.main(["--provider", "gemini"]) == 1
    assert "sk-very-secret" not in capsys.readouterr().out


async def test_concurrent_calls_at_limit_minus_one_allow_exactly_one(env: LLMEnv) -> None:
    """Increment-first: the budget cannot be overshot by racing callers (FR-60)."""
    import asyncio

    provider = load_config().providers["gemini"]
    assert provider.rpd is not None
    for _ in range(provider.rpd - 1):
        await env.store.incr("gemini")
    reasons = await asyncio.gather(
        gateway._skip_reason(provider, env.store), gateway._skip_reason(provider, env.store)
    )
    assert sorted(r or "" for r in reasons) == ["", "over_budget"]
