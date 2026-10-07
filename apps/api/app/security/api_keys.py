"""API keys ``de_<prefix>_<secret>``: sha256(secret + pepper) at rest (FR-07, NFR-05).

CLI: ``python -m app.security.api_keys create --name NAME --scopes items:write,items:read``.
"""

import argparse
import asyncio
import hashlib
import hmac
import logging
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import session_scope
from app.models import ApiKey, Tenant

logger = logging.getLogger(__name__)

Scope = Literal["items:write", "items:read", "decide", "admin"]
ALL_SCOPES: tuple[str, ...] = get_args(Scope)
KEY_TAG = "de"
LAST_USED_INTERVAL = timedelta(minutes=1)
DEFAULT_TENANT_NAME = "default"


@dataclass(frozen=True)
class Principal:
    tenant_id: uuid.UUID
    api_key_id: uuid.UUID
    scopes: frozenset[str]

    def allows(self, scope: str) -> bool:
        return "admin" in self.scopes or scope in self.scopes


@dataclass(frozen=True)
class NewKey:
    full: str
    prefix: str
    hash: str


def hash_secret(secret: str, pepper: str) -> str:
    return hashlib.sha256((secret + pepper).encode()).hexdigest()


def generate_key(pepper: str) -> NewKey:
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    return NewKey(f"{KEY_TAG}_{prefix}_{secret}", prefix, hash_secret(secret, pepper))


def parse_key(raw: str) -> tuple[str, str] | None:
    """Split into (prefix, secret); None when malformed. The secret may contain ``_``."""
    parts = raw.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_TAG:
        return None
    _, prefix, secret = parts
    is_hex = len(prefix) == 8 and all(c in "0123456789abcdef" for c in prefix)
    return (prefix, secret) if is_hex and secret else None


async def authenticate(
    session: AsyncSession, raw: str, pepper: str, now: datetime | None = None
) -> Principal | None:
    """Return the Principal for a valid, unrevoked key; touch last_used_at at most per minute."""
    parsed = parse_key(raw)
    if parsed is None:
        return None
    prefix, secret = parsed
    row = await session.scalar(
        select(ApiKey).where(ApiKey.prefix == prefix, ApiKey.revoked_at.is_(None))
    )
    candidate = hash_secret(secret, pepper)
    stored = row.hash if row is not None else hash_secret("", pepper)  # equalise timing
    if not hmac.compare_digest(candidate, stored) or row is None:
        logger.warning("api key rejected", extra={"key_prefix": prefix})
        return None
    stamp = now or datetime.now(UTC)
    await session.execute(
        update(ApiKey)
        .where(
            ApiKey.id == row.id,
            or_(ApiKey.last_used_at.is_(None), ApiKey.last_used_at < stamp - LAST_USED_INTERVAL),
        )
        .values(last_used_at=stamp)
    )
    await session.commit()
    return Principal(row.tenant_id, row.id, frozenset(row.scopes))


async def create_api_key(
    session: AsyncSession, tenant_id: uuid.UUID, name: str, scopes: list[str], pepper: str
) -> str:
    """Insert a key and return the full key. This is the only time it exists in plain text."""
    unknown = [s for s in scopes if s not in ALL_SCOPES]
    if unknown or not scopes:
        raise ValueError(f"scopes must be a non-empty subset of {ALL_SCOPES}; got {scopes}")
    key = generate_key(pepper)
    session.add(
        ApiKey(tenant_id=tenant_id, prefix=key.prefix, hash=key.hash, scopes=scopes, name=name)
    )
    await session.flush()
    return key.full


async def _default_tenant(session: AsyncSession) -> Tenant:
    tenant = await session.scalar(select(Tenant).order_by(Tenant.created_at).limit(1))
    if tenant is None:
        tenant = Tenant(name=DEFAULT_TENANT_NAME)
        session.add(tenant)
        await session.flush()
    return tenant


async def _cli_create(name: str, scopes: list[str]) -> str:
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with session_scope() as session:
        tenant = await _default_tenant(session)
        return await create_api_key(session, tenant.id, name, scopes, pepper)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.security.api_keys")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an API key (printed once)")
    create.add_argument("--name", required=True)
    create.add_argument("--scopes", default="admin", help="comma-separated; default admin")
    args = parser.parse_args(argv)
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    if not scopes or any(s not in ALL_SCOPES for s in scopes):
        sys.stderr.write(f"error: --scopes must be a non-empty subset of {ALL_SCOPES}\n")
        return 2
    key = asyncio.run(_cli_create(args.name, scopes))
    sys.stdout.write(f"{key}\n")
    sys.stderr.write("Store this key now; it cannot be shown again.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
