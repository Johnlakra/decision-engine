"""Auth and rate-limit dependencies (FR-07, FR-111)."""

from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.redis import get_redis
from app.db.session import get_session
from app.security.api_keys import Principal, Scope, authenticate
from app.security.rate_limit import (
    MemoryRateLimiter,
    RateLimiter,
    RedisRateLimiter,
    ResilientRateLimiter,
)

BEARER = "Bearer "
UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """Redis when REDIS_URL is set (memory on runtime errors), otherwise memory."""
    memory = MemoryRateLimiter()
    client = get_redis()
    if client is None:
        return memory
    return ResilientRateLimiter(RedisRateLimiter(client), memory)


async def get_principal(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Principal:
    header = request.headers.get("authorization", "")
    settings = get_settings()
    principal = None
    if header.startswith(BEARER):
        principal = await authenticate(
            session, header[len(BEARER) :].strip(), settings.api_key_pepper.get_secret_value()
        )
    if principal is None:
        raise HTTPException(401, "Missing or invalid API key", headers=UNAUTHORIZED_HEADERS)
    decision = await limiter.hit(f"key:{principal.api_key_id}", settings.rate_limit_per_min)
    if not decision.allowed:
        raise HTTPException(
            429, "Rate limit exceeded", headers={"Retry-After": str(decision.retry_after_s)}
        )
    return principal


def require_scope(scope: Scope) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory: ``Depends(require_scope("items:write"))``; admin implies all."""

    async def _check(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.allows(scope):
            raise HTTPException(403, f"API key lacks scope '{scope}'")
        return principal

    return _check
