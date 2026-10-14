"""Inbound Telegram updates: forwarded text becomes an item; button presses decide (FR-94).

Called by ``POST /v1/telegram/webhook``. Unknown chats are ignored and their id logged (CLAUDE.md
rule 1). Message text is untrusted data: it is stored raw (FR-06) and never used as an instruction.
"""

import hmac
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.telegram_format import Callback, chat_is_allowed, parse_callback
from app.core.logging import get_logger
from app.db.tenants import ensure_default_tenant
from app.graph import run
from app.graph.errors import InvalidDecision, ItemBusy, ItemNotFound, NotAwaitingApproval
from app.ingest.service import ingest_one
from app.schemas.decision import DecisionIn
from app.schemas.ingest import Hints, IngestItemIn

log = get_logger("app.connectors.telegram")

TELEGRAM_SOURCE = "telegram"
MAX_TITLE_CHARS = 200
TOAST_OK = "Done"
TOAST_REFUSED = "Could not apply that"


class TgChat(BaseModel):
    id: int


class TgMessage(BaseModel):
    message_id: int
    chat: TgChat
    text: str | None = None


class TgCallback(BaseModel):
    id: str
    data: str | None = None
    message: TgMessage | None = None


class TgUpdate(BaseModel):
    update_id: int
    message: TgMessage | None = None
    callback_query: TgCallback | None = None


@dataclass(frozen=True)
class CallbackReply:
    """What the webhook answers a button press with (the toast shown to the user)."""

    callback_id: str
    toast: str


def verify_secret(header_value: str | None, expected: str) -> bool:
    """Constant-time check of X-Telegram-Bot-Api-Secret-Token. Fails closed when unset."""
    if not expected or header_value is None:
        return False
    return hmac.compare_digest(header_value.encode("utf-8"), expected.encode("utf-8"))


def parse_update(body: Any) -> TgUpdate | None:
    """Validated update, or None for a shape we do not handle (logged, never fatal)."""
    try:
        return TgUpdate.model_validate(body)
    except ValidationError:
        log.warning("telegram update ignored: unexpected shape")
        return None


def _first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.splitlines()[0][:MAX_TITLE_CHARS] if stripped else ""


async def ingest_text(session: AsyncSession, tenant_id: uuid.UUID, message: TgMessage) -> bool:
    """Forwarded or typed text becomes a private item. Returns False when there is no text."""
    text = (message.text or "").strip()
    if not text:
        return False
    body = IngestItemIn(
        source=TELEGRAM_SOURCE,
        source_ref=f"{message.chat.id}:{message.message_id}",
        payload={"text": text},
        hints=Hints(title=_first_line(text) or None, body=text),
    )
    await ingest_one(session, tenant_id, body)
    return True


async def apply_callback(callback: Callback, tenant_id: uuid.UUID) -> str:
    """Resume the item's graph with the verdict. Returns the short toast for the button."""
    body = DecisionIn(verdict=callback.verdict)
    try:
        await run.resume_item(callback.item_id, tenant_id, body)
    except (ItemNotFound, NotAwaitingApproval, InvalidDecision, ItemBusy) as error:
        log.info("telegram decision refused", extra={"reason": type(error).__name__})
        return TOAST_REFUSED
    return TOAST_OK


async def handle_callback(callback: TgCallback, tenant_id: uuid.UUID) -> CallbackReply:
    """Apply a button press. Malformed payloads are refused, never guessed at."""
    parsed = parse_callback(callback.data)
    if parsed is None:
        return CallbackReply(callback.id, TOAST_REFUSED)
    return CallbackReply(callback.id, await apply_callback(parsed, tenant_id))


async def handle_update(
    session: AsyncSession, update: TgUpdate, allowed: list[str]
) -> CallbackReply | None:
    """Route one update from an allow-listed chat. Returns a reply for button presses only."""
    chat_id = _chat_of(update)
    if chat_id is None or not chat_is_allowed(chat_id, allowed):
        log.warning("telegram update from unknown chat ignored", extra={"chat_id": chat_id})
        return None
    tenant_id = await ensure_default_tenant(session)
    if update.callback_query is not None:
        return await handle_callback(update.callback_query, tenant_id)
    if update.message is not None:
        await ingest_text(session, tenant_id, update.message)
    return None


def _chat_of(update: TgUpdate) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None and update.callback_query.message is not None:
        return update.callback_query.message.chat.id
    return None
