"""Telegram webhook: ``POST /v1/telegram/webhook`` (FR-94).

Auth is Telegram's secret-token header, not an API key: the bot calls this route, not a client.
Always answers 200 for a well-formed update so Telegram does not redeliver it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.telegram_api import TelegramSendError, answer_callback
from app.connectors.telegram_inbound import (
    CallbackReply,
    handle_update,
    parse_update,
    verify_secret,
)
from app.core.config import get_settings
from app.core.errors import ProblemError
from app.core.logging import get_logger
from app.db.session import get_session

router = APIRouter(prefix="/telegram", tags=["telegram"])
log = get_logger("app.api.telegram")

SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # noqa: S105 - header name, not a credential
Session = Annotated[AsyncSession, Depends(get_session)]
SecretHeader = Annotated[str | None, Header(alias=SECRET_HEADER)]


class TelegramAck(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"ok": True}]})

    ok: bool


async def _toast(reply: CallbackReply) -> None:
    """Dismiss the button spinner. A failed toast never fails the update."""
    try:
        await answer_callback(reply.callback_id, reply.toast)
    except TelegramSendError as error:
        log.warning("telegram toast not sent", extra={"error": str(error)})


@router.post("/webhook", response_model=TelegramAck)
async def webhook(request: Request, session: Session, secret: SecretHeader = None) -> TelegramAck:
    settings = get_settings()
    if not verify_secret(secret, settings.telegram_webhook_secret.get_secret_value()):
        raise ProblemError(403, "Forbidden", "invalid webhook secret")
    try:
        body = await request.json()
    except ValueError as error:
        raise ProblemError(400, "Bad request", "body is not JSON") from error
    update = parse_update(body)
    reply = None
    if update is not None:
        reply = await handle_update(session, update, settings.telegram_allowed_chat_ids)
    await session.commit()
    if reply is not None:
        await _toast(reply)
    return TelegramAck(ok=True)
