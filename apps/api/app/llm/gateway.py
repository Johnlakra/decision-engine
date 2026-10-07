"""The one LLM door: chain, budgets, cool-downs, privacy, structured output, usage log.

Callers use `from app.llm import gateway` then `gateway.complete_json(...)` so the `fake_llm`
fixture can replace the functions (FR-12, FR-60, FR-61, FR-62, NFR-04, NFR-06, NFR-07).
Logs carry ids and provider names only, never message bodies.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from app.core.time import utcnow
from app.db.session import session_scope
from app.llm import providers, usage
from app.llm.budgets import (
    COOLDOWN_SECONDS,
    BudgetStore,
    InMemoryBudgetStore,
    SessionFactory,
    get_budget_store,
    seconds_until_utc_midnight,
)
from app.llm.config import LLMConfig, ProviderConfig, load_config
from app.llm.errors import (
    LLMUnavailable,
    NoPrivateProvider,
    ProviderError,
    StructuredOutputError,
)
from app.llm.privacy import assert_private_safe, select_chain
from app.llm.structured import (
    parse_and_validate,
    prepare_messages,
    repair_messages,
    response_format_for,
)

logger = logging.getLogger(__name__)

Sensitivity = Literal["public", "private"]
PingStatus = Literal["ok", "down", "skipped", "cooldown", "over_budget"]

TIMEOUT_SECONDS = 45.0
DEFAULT_TEMPERATURE = 0.2
CLASSIFY_TEMPERATURE = 0.0
PING_TTL_SECONDS = 300.0
PING_BUDGET_RATIO = 0.8
PING_MAX_TOKENS = 8

# Replaceable in tests; production uses a committing session per usage row.
session_factory: SessionFactory = session_scope


@dataclass
class _Ctx:
    purpose: str
    item_id: str | None
    max_tokens: int
    store: BudgetStore
    log_usage: bool = True

    @property
    def temperature(self) -> float:
        return CLASSIFY_TEMPERATURE if self.purpose == "classify" else DEFAULT_TEMPERATURE


@dataclass
class _Result[T]:
    value: T | None = None
    raw_text: str | None = None  # set when the reply came back but failed validation
    errors: str = ""


def _validate_text(text: str) -> str:
    if not text.strip():
        raise StructuredOutputError("empty reply", text)
    return text


async def _skip_reason(
    provider: ProviderConfig, store: BudgetStore
) -> Literal["cooldown", "over_budget"] | None:
    try:
        if await store.is_cooling(provider.name):
            return "cooldown"
        if provider.rpd is not None and await store.count(provider.name) >= provider.rpd:
            return "over_budget"
    except Exception:
        logger.warning("budget check failed, allowing call", exc_info=True)
    return None


async def _cool_down(store: BudgetStore, provider: str, error: ProviderError) -> None:
    if error.kind == "rate_limit_day":
        seconds = seconds_until_utc_midnight(utcnow())
    elif error.kind in ("rate_limit", "timeout", "server", "auth"):
        seconds = COOLDOWN_SECONDS
    else:
        return
    try:
        await store.cool_down(provider, seconds)
    except Exception:
        logger.warning("cooldown write failed", exc_info=True)


async def _log(
    ctx: _Ctx,
    provider: ProviderConfig,
    *,
    response: providers.ProviderResponse | None,
    started: float,
    error_code: str | None,
) -> None:
    latency_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "llm attempt",
        extra={
            "provider": provider.name,
            "purpose": ctx.purpose,
            "item_id": ctx.item_id,
            "ok": error_code is None,
            "error_code": error_code,
            "latency_ms": latency_ms,
        },
    )
    if not ctx.log_usage:
        return
    await usage.record_usage(
        session_factory,
        provider=provider,
        purpose=ctx.purpose,
        item_id=ctx.item_id,
        prompt_tokens=response.prompt_tokens if response else 0,
        completion_tokens=response.completion_tokens if response else 0,
        latency_ms=latency_ms,
        ok=error_code is None,
        error_code=error_code,
    )


async def _attempt[T](
    ctx: _Ctx,
    provider: ProviderConfig,
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
    validate: Callable[[str], T],
) -> _Result[T]:
    """One logged provider call. Counts against the daily budget even when it fails."""
    try:
        await ctx.store.incr(provider.name)
    except Exception:
        logger.warning("budget incr failed", exc_info=True)
    started = time.perf_counter()
    try:
        response = await providers.call(
            provider,
            messages,
            temperature=ctx.temperature,
            timeout=TIMEOUT_SECONDS,
            max_tokens=ctx.max_tokens,
            response_format=response_format,
        )
    except Exception as exc:
        error = providers.classify_exception(exc)
        await _cool_down(ctx.store, provider.name, error)
        await _log(ctx, provider, response=None, started=started, error_code=error.kind)
        return _Result(errors=error.kind)
    try:
        value = validate(response.text)
    except StructuredOutputError as exc:
        await _log(ctx, provider, response=response, started=started, error_code="invalid_json")
        return _Result(raw_text=exc.raw_text, errors=exc.errors)
    await _log(ctx, provider, response=response, started=started, error_code=None)
    return _Result(value=value)


async def _json_on_provider[M: BaseModel](
    ctx: _Ctx, provider: ProviderConfig, messages: list[dict[str, Any]], schema: type[M]
) -> M | None:
    """Call, validate, and on bad JSON make exactly one repair call on the same provider."""
    prepared = prepare_messages(messages, schema)
    fmt = response_format_for(provider, schema)

    def validate(text: str) -> M:
        return parse_and_validate(text, schema)

    first = await _attempt(ctx, provider, prepared, fmt, validate)
    if first.value is not None or first.raw_text is None:
        return first.value
    repair = repair_messages(prepared, first.raw_text, first.errors)
    return (await _attempt(ctx, provider, repair, fmt, validate)).value


async def _run[T](
    purpose: str,
    chain: list[ProviderConfig],
    *,
    private: bool,
    item_id: str | None,
    max_tokens: int,
    store: BudgetStore,
    attempt_one: Callable[[_Ctx, ProviderConfig], Any],
    log_usage: bool = True,
) -> T:
    ctx = _Ctx(purpose, item_id, max_tokens, store, log_usage)
    for provider in chain:
        reason = await _skip_reason(provider, store)
        if reason:
            logger.info("llm provider skipped", extra={"provider": provider.name, "reason": reason})
            continue
        value = await attempt_one(ctx, provider)
        if value is not None:
            return value  # type: ignore[no-any-return]
    names = [p.name for p in chain]
    if private:
        raise NoPrivateProvider(f"no private provider answered (tried {names})")
    raise LLMUnavailable(f"all providers failed for {purpose!r} (tried {names})")


def _plan(
    purpose: str, sensitivity: Sensitivity, language: str, max_tokens: int | None
) -> tuple[list[ProviderConfig], int, BudgetStore, LLMConfig]:
    config = load_config()
    chain = select_chain(purpose, sensitivity=sensitivity, language=language, config=config)
    if sensitivity == "private":
        assert_private_safe(chain)
    return chain, max_tokens or config.max_tokens_for(purpose), get_budget_store(), config


async def complete_json[M: BaseModel](
    purpose: str,
    schema: type[M],
    messages: list[dict[str, Any]],
    *,
    sensitivity: Sensitivity,
    language: str = "en",
    item_id: str | None = None,
    max_tokens: int | None = None,
) -> M:
    """Structured completion validated against `schema` (LLMUnavailable / NoPrivateProvider)."""
    chain, tokens, store, _ = _plan(purpose, sensitivity, language, max_tokens)

    async def one(ctx: _Ctx, provider: ProviderConfig) -> M | None:
        return await _json_on_provider(ctx, provider, messages, schema)

    return await _run(
        purpose,
        chain,
        private=sensitivity == "private",
        item_id=item_id,
        max_tokens=tokens,
        store=store,
        attempt_one=one,
    )


async def complete_text(
    purpose: str,
    messages: list[dict[str, Any]],
    *,
    sensitivity: Sensitivity,
    language: str = "en",
    item_id: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """Plain text completion. Raises LLMUnavailable / NoPrivateProvider."""
    chain, tokens, store, _ = _plan(purpose, sensitivity, language, max_tokens)

    async def one(ctx: _Ctx, provider: ProviderConfig) -> str | None:
        return (await _attempt(ctx, provider, messages, None, _validate_text)).value

    return await _run(
        purpose,
        chain,
        private=sensitivity == "private",
        item_id=item_id,
        max_tokens=tokens,
        store=store,
        attempt_one=one,
    )


async def complete_json_on[M: BaseModel](
    provider_name: str, schema: type[M], messages: list[dict[str, Any]]
) -> M:
    """Smoke-test path: one named provider, in-memory budget, no usage row."""
    config = load_config()
    provider = config.providers.get(provider_name)
    if provider is None or not provider.available:
        raise LLMUnavailable(f"provider {provider_name!r} is not configured")

    async def one(ctx: _Ctx, p: ProviderConfig) -> M | None:
        return await _json_on_provider(ctx, p, messages, schema)

    return await _run(
        "smoke",
        [provider],
        private=False,
        item_id=None,
        max_tokens=config.max_tokens_for("classify"),
        store=InMemoryBudgetStore(),
        attempt_one=one,
        log_usage=False,
    )


_ping_cache: dict[str, tuple[float, PingStatus]] = {}
_ping_clock: Callable[[], float] = time.monotonic


def reset_ping_cache() -> None:
    _ping_cache.clear()


async def _ping_one(name: str, config: LLMConfig, store: BudgetStore) -> PingStatus:
    provider = config.providers.get(name)
    if provider is None or not provider.available:
        return "skipped"
    cached = _ping_cache.get(name)
    if cached and _ping_clock() - cached[0] < PING_TTL_SECONDS:
        return cached[1]
    if await store.is_cooling(name):
        return "cooldown"
    if provider.rpd and await store.count(name) >= provider.rpd * PING_BUDGET_RATIO:
        return "over_budget"  # do not spend scarce quota on health checks
    ctx = _Ctx("ping", None, PING_MAX_TOKENS, store)
    result = await _attempt(
        ctx, provider, [{"role": "user", "content": "ping"}], None, _validate_text
    )
    status: PingStatus = "ok" if result.value is not None else "down"
    _ping_cache[name] = (_ping_clock(), status)
    return status


async def ping(provider: str | None = None) -> dict[str, PingStatus]:
    """Provider health for /health/deep, cached 5 min; skips providers near their daily budget."""
    config = load_config()
    store = get_budget_store()
    names = [provider] if provider else list(config.providers)
    result: dict[str, PingStatus] = {}
    for name in names:
        try:
            result[name] = await _ping_one(name, config, store)
        except Exception:
            logger.warning("ping failed", exc_info=True, extra={"provider": name})
            result[name] = "down"
    return result
