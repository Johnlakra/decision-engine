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
from functools import partial
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx
from sqlalchemy import any_, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ids import new_id
from app.core.time import utcnow
from app.integrations.pinned import pinned_transport
from app.integrations.ssrf import Resolver, UnsafeUrl, check_url
from app.models import Decision, Item, Job, WebhookDelivery, WebhookSubscription
from app.models.enums import DeliveryStatus, JobKind
from app.schemas.items import item_to_public
from app.security.crypto import CryptoNotConfigured, DecryptError, decrypt
from app.security.hmac import sign
from app.workers import queue

log = logging.getLogger(__name__)

RETRY_SCHEDULE_S: tuple[int, ...] = (60, 300, 1800, 7200)
MAX_ATTEMPTS = len(RETRY_SCHEDULE_S) + 1
ACTION_EXTRA_KEYS = ("action", "ok")
MAX_RESPONSE_BYTES = 64 * 1024  # response bodies are read up to this, then discarded


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


@dataclass(frozen=True)
class SendRequest:
    """Plain values for one attempt, so no ORM row is touched while the POST is in flight."""

    delivery_id: uuid.UUID
    event: str
    payload: dict[str, Any]
    url: str
    secret_enc: str


@dataclass(frozen=True)
class SendResult:
    """What one HTTP attempt produced; ``status_code`` is None when no response arrived."""

    status_code: int | None
    permanent: bool = False  # retrying cannot help (e.g. the stored secret cannot be decrypted)


async def _post_bounded(
    url: str,
    body: bytes,
    headers: dict[str, str],
    *,
    transport: httpx.AsyncBaseTransport | None,
) -> int:
    """POST and return the status code. The response body is read up to a cap, then dropped.

    The status code is kept even when the drain is cut short by the total timeout or a
    network error, so a 2xx with a hostile body still counts as delivered.
    """
    timeout = get_settings().webhook_timeout_seconds
    status_code: int | None = None
    try:
        async with asyncio.timeout(timeout):
            async with (
                httpx.AsyncClient(
                    timeout=timeout, follow_redirects=False, trust_env=False, transport=transport
                ) as client,
                client.stream("POST", url, content=body, headers=headers) as response,
            ):
                status_code = response.status_code
                read = 0
                async for chunk in response.aiter_raw():
                    read += len(chunk)
                    if read >= MAX_RESPONSE_BYTES:
                        break
    except (httpx.HTTPError, TimeoutError):
        if status_code is None:
            raise
    if status_code is None:  # unreachable: the except block re-raises without a status
        raise httpx.TransportError("no response")
    return status_code


async def send_once(
    request: SendRequest,
    *,
    resolver: Resolver | None = None,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> SendResult:
    """One HTTP attempt using plain values only (no ORM rows, so no DB lock is needed).

    The connection is pinned to the addresses the SSRF check vetted (no second DNS lookup),
    and proxy environment variables are ignored, so neither can route around the check.
    """
    settings = get_settings()
    try:
        vetted = await asyncio.to_thread(
            partial(
                check_url,
                request.url,
                allow_private=settings.webhook_allow_private_urls,
                resolver=resolver,
            )
        )
    except UnsafeUrl:
        log.warning("webhook delivery=%s refused: unsafe url", request.delivery_id)
        return SendResult(None)
    body = serialize(request.payload)
    try:
        secret = decrypt(request.secret_enc).encode()
    except (DecryptError, CryptoNotConfigured) as exc:
        log.error(
            "webhook delivery=%s secret unusable: %s", request.delivery_id, type(exc).__name__
        )
        return SendResult(None, permanent=True)
    headers = {
        "Content-Type": "application/json",
        "X-DE-Signature": sign(secret, body),
        "X-DE-Event": request.event,
        "X-DE-Delivery": str(request.delivery_id),
    }
    hostname = urlsplit(request.url).hostname or ""
    transport = (
        pinned_transport(hostname, vetted, network_backend=network_backend) if vetted else None
    )
    try:
        status_code = await _post_bounded(request.url, body, headers, transport=transport)
    except (httpx.HTTPError, TimeoutError) as exc:
        log.info("webhook delivery=%s failed: %s", request.delivery_id, type(exc).__name__)
        return SendResult(None)
    return SendResult(status_code)


def apply_result(delivery: WebhookDelivery, result: SendResult, now: datetime) -> DeliveryOutcome:
    """Record one attempt's result on the delivery row."""
    status_code = result.status_code
    if result.permanent:
        delivery.attempts += 1
        delivery.last_status_code = None
        delivery.status = DeliveryStatus.FAILED.value
        return DeliveryOutcome(delivered=False)
    if status_code is not None and 200 <= status_code < 300:
        delivery.attempts += 1
        delivery.last_status_code = status_code
        delivery.status = DeliveryStatus.DELIVERED.value
        return DeliveryOutcome(delivered=True)
    if status_code is not None:
        log.info("webhook delivery=%s got status %s", delivery.id, status_code)
    return _record_failure(delivery, status_code, now)


async def deliver_once(
    delivery: WebhookDelivery,
    subscription: WebhookSubscription,
    *,
    now: datetime | None = None,
    resolver: Resolver | None = None,
    network_backend: httpcore.AsyncNetworkBackend | None = None,
) -> DeliveryOutcome:
    """Make one attempt and update the delivery row. Never raises for HTTP/network failures."""
    request = SendRequest(
        delivery_id=delivery.id,
        event=delivery.event,
        payload=delivery.payload,
        url=subscription.url,
        secret_enc=subscription.secret_enc,
    )
    result = await send_once(
        request,
        resolver=resolver,
        network_backend=network_backend,
    )
    return apply_result(delivery, result, now or utcnow())


async def _lock_pending(session: AsyncSession, job: Job) -> WebhookDelivery | None:
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(
            WebhookDelivery.id == uuid.UUID(str(job.payload["delivery_id"])),
            WebhookDelivery.tenant_id == job.tenant_id,
        )
        .with_for_update()
    )
    if delivery is None or delivery.status != DeliveryStatus.PENDING.value:
        return None
    return delivery


async def deliver(session: AsyncSession, job: Job) -> None:
    """Run the attempt for ``job.payload['delivery_id']`` and schedule a retry if needed.

    Two short transactions around the HTTP call: the first reads what to send and commits
    (releasing the row lock), the second re-locks the row and records the outcome. The job
    queue already gives each job to a single worker, so nothing is held during the POST.
    """
    delivery = await _lock_pending(session, job)
    if delivery is None:
        return
    subscription = await session.get(WebhookSubscription, delivery.subscription_id)
    if subscription is None or not subscription.enabled:
        delivery.status = DeliveryStatus.FAILED.value
        return
    delivery_id = delivery.id
    request = SendRequest(
        delivery_id=delivery_id,
        event=delivery.event,
        payload=dict(delivery.payload),
        url=subscription.url,
        secret_enc=subscription.secret_enc,
    )
    await session.commit()  # release the FOR UPDATE lock before talking to the subscriber
    result = await send_once(request)
    delivery = await _lock_pending(session, job)
    if delivery is None:
        return
    outcome = apply_result(delivery, result, utcnow())
    if outcome.retry_at is not None:
        await queue.enqueue(
            session,
            tenant_id=job.tenant_id,
            kind=JobKind.WEBHOOK,
            item_id=job.item_id,
            payload={"op": "deliver", "delivery_id": str(delivery_id)},
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
