"""Outbound webhooks: fan-out and delivery jobs (FR-42, NFR-05, ADR 0004).

``handle_webhook_job`` serves ``jobs(kind=webhook)`` with two ops. ``fanout`` writes one
``webhook_deliveries`` row and one ``deliver`` job per subscription. ``deliver`` POSTs the
stored body, re-signed with a fresh timestamp, and reschedules itself on failure.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import any_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.time import utcnow
from app.integrations.ssrf import UnsafeUrl, check_url
from app.models import Decision, Item, Job, WebhookDelivery, WebhookSubscription
from app.models.enums import DeliveryStatus, JobKind
from app.schemas.items import item_to_public
from app.security.crypto import decrypt
from app.security.hmac import sign
from app.workers import queue

log = logging.getLogger(__name__)

RETRY_SCHEDULE_S: tuple[int, ...] = (60, 300, 1800, 7200)
MAX_ATTEMPTS = len(RETRY_SCHEDULE_S) + 1
ACTION_EXTRA_KEYS = ("action", "ok")


@dataclass(frozen=True)
class DeliveryOutcome:
    """Result of one attempt. ``retry_at`` is set only when another attempt is due."""

    delivered: bool
    retry_at: datetime | None = None


def serialize(envelope: dict[str, Any]) -> bytes:
    """Deterministic bytes: every retry sends and signs the same body."""
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def build_envelope(
    *,
    event: str,
    event_id: str,
    created_at: datetime,
    item: Item,
    last_decision: Decision | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Envelope per API.md. ``data`` is item_to_public (no raw, hints, callback_url)."""
    data = item_to_public(item, last_decision).model_dump(mode="json")
    if event == "action.done" and extra:
        data.update({key: extra[key] for key in ACTION_EXTRA_KEYS if key in extra})
    return {
        "event": event,
        "id": event_id,
        "created_at": created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": data,
    }


async def _last_decision(session: AsyncSession, item: Item) -> Decision | None:
    return await session.scalar(
        select(Decision)
        .where(
            Decision.item_id == item.id,
            Decision.tenant_id == item.tenant_id,
            Decision.undone_at.is_(None),
        )
        .order_by(Decision.created_at.desc())
        .limit(1)
    )


async def fanout(session: AsyncSession, job: Job) -> int:
    """Create deliveries for every enabled matching subscription; returns how many."""
    payload = job.payload
    event = str(payload["event"])
    item = await session.scalar(
        select(Item).where(Item.id == job.item_id, Item.tenant_id == job.tenant_id)
    )
    if item is None:
        log.warning("webhook fanout: item gone job=%s", job.id)
        return 0
    subscriptions = (
        await session.scalars(
            select(WebhookSubscription).where(
                WebhookSubscription.tenant_id == job.tenant_id,
                WebhookSubscription.enabled.is_(True),
                literal(event) == any_(WebhookSubscription.events),
            )
        )
    ).all()
    if not subscriptions:
        return 0
    now = utcnow()
    envelope = build_envelope(
        event=event,
        event_id=str(payload["event_id"]),
        created_at=now,
        item=item,
        last_decision=await _last_decision(session, item),
        extra=payload.get("extra") or {},
    )
    for subscription in subscriptions:
        delivery = WebhookDelivery(
            id=new_id(),
            tenant_id=job.tenant_id,
            subscription_id=subscription.id,
            event=event,
            payload=envelope,
            status=DeliveryStatus.PENDING.value,
            attempts=0,
            next_attempt_at=now,
        )
        session.add(delivery)
        await session.flush()
        await queue.enqueue(
            session,
            tenant_id=job.tenant_id,
            kind=JobKind.WEBHOOK,
            item_id=item.id,
            payload={"op": "deliver", "delivery_id": str(delivery.id)},
        )
    return len(subscriptions)


def _record_failure(
    delivery: WebhookDelivery, status_code: int | None, now: datetime
) -> DeliveryOutcome:
    delivery.attempts += 1
    delivery.last_status_code = status_code
    if delivery.attempts >= MAX_ATTEMPTS:
        delivery.status = DeliveryStatus.FAILED.value
        return DeliveryOutcome(delivered=False)
    delivery.next_attempt_at = now + timedelta(seconds=RETRY_SCHEDULE_S[delivery.attempts - 1])
    return DeliveryOutcome(delivered=False, retry_at=delivery.next_attempt_at)


async def deliver_once(
    delivery: WebhookDelivery, subscription: WebhookSubscription, *, now: datetime | None = None
) -> DeliveryOutcome:
    """Make one attempt and update the delivery row. Never raises for HTTP/network failures."""
    moment = now or utcnow()
    settings = get_settings()
    try:
        await asyncio.to_thread(
            check_url, subscription.url, allow_private=settings.webhook_allow_private_urls
        )
    except UnsafeUrl:
        log.warning("webhook delivery=%s refused: unsafe url", delivery.id)
        return _record_failure(delivery, None, moment)
    body = serialize(delivery.payload)
    secret = decrypt(subscription.secret_enc).encode()
    headers = {
        "Content-Type": "application/json",
        "X-DE-Signature": sign(secret, body),
        "X-DE-Event": delivery.event,
        "X-DE-Delivery": str(delivery.id),
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.webhook_timeout_seconds, follow_redirects=False
        ) as client:
            response = await client.post(subscription.url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        log.info("webhook delivery=%s failed: %s", delivery.id, type(exc).__name__)
        return _record_failure(delivery, None, moment)
    if 200 <= response.status_code < 300:
        delivery.attempts += 1
        delivery.last_status_code = response.status_code
        delivery.status = DeliveryStatus.DELIVERED.value
        return DeliveryOutcome(delivered=True)
    log.info("webhook delivery=%s got status %s", delivery.id, response.status_code)
    return _record_failure(delivery, response.status_code, moment)


async def deliver(session: AsyncSession, job: Job) -> None:
    """Run the attempt for ``job.payload['delivery_id']`` and schedule a retry if needed."""
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.id == uuid.UUID(str(job.payload["delivery_id"])),
            WebhookDelivery.tenant_id == job.tenant_id,
        )
        .with_for_update()
    )
    if delivery is None or delivery.status != DeliveryStatus.PENDING.value:
        return
    subscription = await session.get(WebhookSubscription, delivery.subscription_id)
    if subscription is None or not subscription.enabled:
        delivery.status = DeliveryStatus.FAILED.value
        return
    outcome = await deliver_once(delivery, subscription)
    if outcome.retry_at is not None:
        await queue.enqueue(
            session,
            tenant_id=job.tenant_id,
            kind=JobKind.WEBHOOK,
            item_id=job.item_id,
            payload={"op": "deliver", "delivery_id": str(delivery.id)},
            run_at=outcome.retry_at,
        )


async def handle_webhook_job(session: AsyncSession, job: Job) -> None:
    """Entry point the worker registers for ``JobKind.WEBHOOK``."""
    op = job.payload.get("op")
    if op == "fanout":
        await fanout(session, job)
    elif op == "deliver":
        await deliver(session, job)
    else:
        raise ValueError(f"unknown webhook op: {op!r}")
