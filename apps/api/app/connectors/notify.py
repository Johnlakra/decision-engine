"""Telegram notifier pass: urgent pings and the daily digest (FR-43, FR-94).

Run every few minutes from cron: ``python -m app.connectors.notify``. Each run:
1. pings each owner once for every urgent item still awaiting approval, within quiet hours and the
   daily cap (buttons approve or reject the item, see telegram_inbound);
2. sends one digest per local day at the digest hour, listing what still waits for approval.
A failed send leaves the item unmarked, so the next run retries it.
"""

import asyncio
import html
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.notify_policy import (
    DIGEST_SENT_ON_KEY,
    MIN_URGENCY_FOR_PING,
    NotifySettings,
    digest_due,
    digest_sent_on_from,
    may_ping,
    settings_from,
)
from app.connectors.telegram_api import TelegramSendError, send_message
from app.connectors.telegram_format import ping_keyboard, ping_text, title_of
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.db.tenants import DEFAULT_TENANT
from app.models import Item, Tenant, TenantSettings
from app.models.enums import ItemStatus

log = get_logger("app.connectors.notify")

PING_BATCH = 20  # items considered per run; the rest wait for the next run
DIGEST_MAX_LINES = 10
DIGEST_HEADING = "<b>Waiting for approval</b>"


@dataclass(frozen=True)
class NotifyReport:
    pings_sent: int
    digest_sent: bool


def _local_day_start_utc(local_now: datetime) -> datetime:
    midnight = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    return midnight.astimezone(UTC)


async def _tenant_settings(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, object]:
    row = await session.get(TenantSettings, tenant_id)
    return dict(row.settings) if row is not None else {}


async def _pending(session: AsyncSession, tenant_id: uuid.UUID, *, urgent: bool) -> list[Item]:
    stmt = select(Item).where(
        Item.tenant_id == tenant_id,
        Item.status == ItemStatus.AWAITING_APPROVAL.value,
    )
    if urgent:
        stmt = stmt.where(Item.notified_at.is_(None), Item.urgency >= MIN_URGENCY_FOR_PING)
        stmt = stmt.order_by(Item.received_at).limit(PING_BATCH)
    else:
        stmt = stmt.where(Item.digested_at.is_(None)).order_by(Item.received_at)
    return list((await session.execute(stmt)).scalars().all())


async def _pings_since(session: AsyncSession, tenant_id: uuid.UUID, since: datetime) -> int:
    stmt = (
        select(func.count())
        .select_from(Item)
        .where(Item.tenant_id == tenant_id, Item.notified_at >= since)
    )
    return int((await session.execute(stmt)).scalar_one())


async def _send_everywhere(
    chats: Sequence[str],
    text: str,
    keyboard: list[list[dict[str, str]]] | None,
    transport: httpx.AsyncBaseTransport | None,
) -> bool:
    """Send to every owner chat. True only when every send succeeded."""
    ok = True
    for chat in chats:
        try:
            await send_message(chat, text, keyboard, transport=transport)
        except TelegramSendError as error:
            ok = False
            log.warning("telegram notify failed", extra={"error": str(error)})
    return ok


async def _send_ping(
    session: AsyncSession,
    item: Item,
    now: datetime,
    chats: Sequence[str],
    transport: httpx.AsyncBaseTransport | None,
) -> bool:
    text = ping_text(item.content, item.decision, (item.hints or {}).get("url"))
    if not await _send_everywhere(chats, text, ping_keyboard(item.id), transport):
        return False
    item.notified_at = now
    await session.flush()
    return True


def _digest_text(items: Sequence[Item]) -> str:
    lines = [DIGEST_HEADING]
    for item in items[:DIGEST_MAX_LINES]:
        lines.append(f"• {html.escape(title_of(item.content))}")
    hidden = len(items) - DIGEST_MAX_LINES
    if hidden > 0:
        lines.append(f"…and {hidden} more in the queue")
    return "\n".join(lines)


async def _send_digest(
    session: AsyncSession,
    items: Sequence[Item],
    now: datetime,
    chats: Sequence[str],
    transport: httpx.AsyncBaseTransport | None,
) -> bool:
    if not await _send_everywhere(chats, _digest_text(items), None, transport):
        return False
    for item in items:
        item.digested_at = now
    await session.flush()
    return True


async def _record_digest_day(session: AsyncSession, tenant_id: uuid.UUID, local_date: str) -> None:
    raw = await _tenant_settings(session, tenant_id)
    updated = {**raw, DIGEST_SENT_ON_KEY: local_date}
    row = await session.get(TenantSettings, tenant_id)
    if row is None:
        session.add(TenantSettings(tenant_id=tenant_id, settings=updated))
    else:
        row.settings = updated
    await session.flush()


async def run_notifications(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    tz_name: str,
    now: datetime,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> NotifyReport:
    """One notifier pass for a tenant. Caller commits."""
    chats = get_settings().telegram_allowed_chat_ids
    raw = await _tenant_settings(session, tenant_id)
    settings: NotifySettings = settings_from(raw)
    local_now = now.astimezone(ZoneInfo(tz_name))
    pings = 0
    pings_today = await _pings_since(session, tenant_id, _local_day_start_utc(local_now))
    for item in await _pending(session, tenant_id, urgent=True):
        if not may_ping(local_now.hour, pings_today + pings, settings):
            break
        if await _send_ping(session, item, now, chats, transport):
            pings += 1
    digest_sent = False
    if digest_due(local_now, digest_sent_on_from(raw), settings):
        waiting = await _pending(session, tenant_id, urgent=False)
        if not waiting or await _send_digest(session, waiting, now, chats, transport):
            await _record_digest_day(session, tenant_id, local_now.date().isoformat())
            digest_sent = True
    return NotifyReport(pings_sent=pings, digest_sent=digest_sent)


async def _default_tenant(session: AsyncSession) -> Tenant | None:
    return await session.scalar(select(Tenant).where(Tenant.name == DEFAULT_TENANT).limit(1))


async def run() -> NotifyReport | None:
    async with session_scope() as session:
        tenant = await _default_tenant(session)
        if tenant is None:
            return None
        return await run_notifications(session, tenant.id, tenant.timezone, utcnow())


def main() -> int:
    report = asyncio.run(run())
    if report is None:
        print("notify: no default tenant yet")  # noqa: T201 - CLI output
        return 0
    digest = "sent" if report.digest_sent else "no"
    print(f"notify: {report.pings_sent} pings, digest={digest}")  # noqa: T201 - CLI output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
