"""LLM gateway errors. Callers only ever see LLMUnavailable / NoPrivateProvider (FR-12, FR-61)."""

from typing import Literal

ProviderErrorKind = Literal[
    "rate_limit", "rate_limit_day", "timeout", "server", "auth", "bad_request", "other"
]


class LLMUnavailable(Exception):  # noqa: N818 - public name fixed by ARCHITECTURE section 5
    """Every provider in the chain failed, was skipped or is over budget."""


class NoPrivateProvider(LLMUnavailable):
    """A private item cannot be served: no private_ok provider is configured or reachable.

    The caller parks the item; it is never sent to a free tier (CLAUDE.md privacy rule).
    """


class ProviderError(Exception):
    """One failed provider attempt, already classified (see providers.classify_exception)."""

    def __init__(self, kind: ProviderErrorKind, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind: ProviderErrorKind = kind


class StructuredOutputError(Exception):
    """Model output was not valid JSON for the schema."""

    def __init__(self, errors: str, raw_text: str) -> None:
        super().__init__(errors)
        self.errors = errors
        self.raw_text = raw_text
