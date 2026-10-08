"""Subscription service behind /v1/subscriptions (FR-42). Router wiring lives in step W."""

import asyncio
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ids import new_id
from app.integrations.events import EVENT_NAMES
from app.integrations.ssrf import check_url
from app.models import WebhookDelivery, WebhookSubscription
from app.security.crypto import encrypt

MIN_SECRET_CHARS = 16


class InvalidSubscription(ValueError):  # noqa: N818 - maps to HTTP 422
    """Subscription input failed validation."""


async def create_subscription(
    session: AsyncSession, *, tenant_id: uuid.UUID, url: str, events: Sequence[str], secret: str
) -> WebhookSubscription:
    """Validate (SSRF guard, event names, secret length), encrypt the secret and store."""
    unknown = sorted(set(events) - EVENT_NAMES)
    if not events or unknown:
        raise InvalidSubscription(f"events must be a non-empty subset of {sorted(EVENT_NAMES)}")
    if len(secret) < MIN_SECRET_CHARS:
        raise InvalidSubscription(f"secret must be at least {MIN_SECRET_CHARS} characters")
    allow_private = get_settings().webhook_allow_private_urls
    try:
        await asyncio.to_thread(check_url, url, allow_private=allow_private)
    except ValueError as exc:
        raise InvalidSubscription(str(exc)) from exc
    subscription = WebhookSubscription(
        id=new_id(),
        tenant_id=tenant_id,
        url=url,
        events=sorted(set(events)),
        secret_enc=encrypt(secret),
        enabled=True,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def list_subscriptions(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[WebhookSubscription]:
    rows = await session.scalars(
        select(WebhookSubscription)
        .where(WebhookSubscription.tenant_id == tenant_id)
        .order_by(WebhookSubscription.created_at)
    )
    return list(rows)


async def delete_subscription(
    session: AsyncSession, *, tenant_id: uuid.UUID, subscription_id: uuid.UUID
) -> bool:
    """True when a row of this tenant was deleted."""
    result = await session.execute(
        delete(WebhookSubscription)
        .where(
            WebhookSubscription.id == subscription_id, WebhookSubscription.tenant_id == tenant_id
        )
        .returning(WebhookSubscription.id)
    )
    return result.first() is not None


async def list_deliveries(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: str | None = None,
    limit: int = 100,
) -> list[WebhookDelivery]:
    """Newest first; ``status='failed'`` is the dead-letter view."""
    stmt = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(WebhookDelivery.status == status)
    rows = await session.scalars(stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit))
    return list(rows)
