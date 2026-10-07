"""The ONLY module that imports litellm. `call` is the seam tests replace (FR-60, NFR-04)."""

from dataclasses import dataclass
from typing import Any

from app.llm.config import ProviderConfig
from app.llm.errors import ProviderError, ProviderErrorKind

_DAY_MARKERS = ("per day", "perday", "daily", "rpd", "tpd", "per-day")
_QUOTA_STATUS = 402  # OpenRouter: out of credits behaves like a daily limit


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


def classify_exception(exc: BaseException) -> ProviderError:
    """Map a litellm/httpx/asyncio exception to a ProviderError kind (no body text is kept)."""
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    kind: ProviderErrorKind
    if isinstance(exc, TimeoutError) or status == 408 or "timeout" in type(exc).__name__.lower():
        kind = "timeout"
    elif status == 429 or "ratelimit" in type(exc).__name__.lower():
        kind = "rate_limit_day" if any(m in text for m in _DAY_MARKERS) else "rate_limit"
    elif status == _QUOTA_STATUS:
        kind = "rate_limit_day"
    elif status in (401, 403):
        kind = "auth"
    elif isinstance(status, int) and 400 <= status < 500:
        kind = "bad_request"
    elif isinstance(status, int) and status >= 500:
        kind = "server"
    elif "connection" in type(exc).__name__.lower():
        kind = "server"
    else:
        kind = "other"
    return ProviderError(kind, type(exc).__name__)


def _extract(response: Any, fallback_model: str) -> ProviderResponse:
    choice = response.choices[0]
    text = getattr(choice.message, "content", None) or ""
    usage = getattr(response, "usage", None)
    return ProviderResponse(
        text=str(text),
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        model=str(getattr(response, "model", "") or fallback_model),
    )


async def call(
    provider: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    timeout: float,  # noqa: ASYNC109 - passed straight to litellm
    max_tokens: int,
    response_format: dict[str, Any] | None = None,
) -> ProviderResponse:
    """One completion on one provider. Raises ProviderError only."""
    import litellm  # the single litellm import in the codebase

    kwargs: dict[str, Any] = {
        "model": provider.litellm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
        "num_retries": 0,
    }
    if provider.api_key is not None:
        kwargs["api_key"] = provider.api_key.get_secret_value()
    if provider.api_base:
        kwargs["api_base"] = provider.api_base
    if response_format is not None:
        kwargs["response_format"] = response_format
    try:
        response = await litellm.acompletion(**kwargs)
    except Exception as exc:
        raise classify_exception(exc) from exc
    return _extract(response, provider.litellm_model)
