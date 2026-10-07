"""Privacy routing: private items reach only private_ok providers (CLAUDE.md, FR-61, NFR-04).

Two independent guards: the yaml/env `private_ok` flag and a hard deny-list of free-tier
providers that no configuration can override.
"""

from collections.abc import Iterable
from typing import Literal

from app.llm.config import PRIVATE_CHAIN, LLMConfig, ProviderConfig, load_config
from app.llm.errors import LLMUnavailable, NoPrivateProvider

# Free tiers that may train on or log prompts: never private, whatever the config says.
NEVER_PRIVATE = frozenset({"gemini", "groq", "cerebras", "openrouter", "sarvam"})


def is_private_ok(provider: ProviderConfig) -> bool:
    return provider.private_ok and provider.name not in NEVER_PRIVATE


def filter_private(providers: Iterable[ProviderConfig]) -> list[ProviderConfig]:
    return [p for p in providers if is_private_ok(p)]


def assert_private_safe(providers: Iterable[ProviderConfig]) -> None:
    """Last line of defence before a private prompt leaves the process."""
    offenders = [p.name for p in providers if not is_private_ok(p)]
    if offenders:
        raise NoPrivateProvider(f"private call routed to non-private provider(s): {offenders}")


def select_chain(
    purpose: str,
    *,
    sensitivity: Literal["public", "private"],
    language: str = "en",
    config: LLMConfig | None = None,
) -> list[ProviderConfig]:
    """Ordered usable providers for one call.

    Private: only `chains.private` members that are private_ok (raises NoPrivateProvider if none).
    Public: Indic text purposes try `chains.indic` first; providers without keys are skipped.
    """
    cfg = config or load_config()
    if sensitivity == "private":
        members = [cfg.providers[n] for n in cfg.chains[PRIVATE_CHAIN] if n in cfg.providers]
        usable = filter_private(p for p in members if p.available)
        if not usable:
            raise NoPrivateProvider("no private provider is configured (set OLLAMA_URL)")
        return usable
    if purpose not in cfg.chains or purpose in (PRIVATE_CHAIN, "indic"):
        raise ValueError(f"unknown LLM purpose: {purpose!r}")
    names = list(cfg.chains[purpose])
    if language.lower() in cfg.indic_languages and purpose in cfg.indic_purposes:
        names = [*cfg.chains["indic"], *names]
    seen: set[str] = set()
    chain: list[ProviderConfig] = []
    for name in names:
        provider = cfg.providers.get(name)
        if provider is None or name in seen or not provider.available:
            continue
        seen.add(name)
        chain.append(provider)
    if not chain:
        raise LLMUnavailable(f"no provider configured for purpose {purpose!r} (missing API keys)")
    return chain
