"""Minimal Telegram Bot API client: send a message, answer a button press (FR-43, FR-94).

The bot token sits in the request path, and httpx error text can echo that path. So transport
errors are re-raised as ``TelegramSendError`` with only the exception class name, never the URL.
"""

from typing import Any

import httpx

from app.core.config import get_settings

TELEGRAM_API_BASE = "https://api.telegram.org"
API_TIMEOUT_S = 10.0
OK_STATUS = 200
MAX_TOAST_CHARS = 200


class TelegramSendError(RuntimeError):
    """A Bot API call failed. The message never contains the token or the request URL."""


def _method_url(method: str, token: str) -> str:
    return f"{TELEGRAM_API_BASE}/bot{token}/{method}"


async def _call(
    method: str, payload: dict[str, Any], *, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    token = get_settings().telegram_bot_token.get_secret_value()
    if not token:
        raise TelegramSendError("TELEGRAM_BOT_TOKEN is not configured")
    try:
        async with httpx.AsyncClient(
            timeout=API_TIMEOUT_S, follow_redirects=False, trust_env=False, transport=transport
        ) as client:
            response = await client.post(_method_url(method, token), json=payload)
    except httpx.HTTPError as error:
        raise TelegramSendError(f"{method} failed: {type(error).__name__}") from None
    if response.status_code != OK_STATUS:
        raise TelegramSendError(f"{method} returned HTTP {response.status_code}")


async def send_message(
    chat_id: str,
    text: str,
    keyboard: list[list[dict[str, str]]] | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Send an HTML message with optional inline buttons. Caller formats and escapes ``text``."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    await _call("sendMessage", payload, transport=transport)


async def answer_callback(
    callback_id: str, text: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Dismiss the button spinner with a short toast."""
    await _call(
        "answerCallbackQuery",
        {"callback_query_id": callback_id, "text": text[:MAX_TOAST_CHARS]},
        transport=transport,
    )
