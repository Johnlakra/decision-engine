"""Telegram message text and inline buttons (FR-43, FR-94). Pure: no network, no DB.

Callback data is ``de:<code>:<item uuid>`` (41 bytes, under Telegram's 64-byte limit).
Every remote string is HTML-escaped before it reaches Telegram (parse_mode=HTML).
"""

import html
import uuid
from dataclasses import dataclass
from typing import Any

from app.models.enums import Verdict

CALLBACK_PREFIX = "de"
CODE_APPROVE = "a"
CODE_REJECT = "r"
CODE_TO_VERDICT: dict[str, Verdict] = {CODE_APPROVE: Verdict.APPROVE, CODE_REJECT: Verdict.REJECT}
MAX_TEXT_CHARS = 3500  # Telegram caps messages at 4096 characters; keep headroom
MAX_TITLE_CHARS = 200
MAX_RATIONALE_CHARS = 600
APPROVE_LABEL = "Save and act"
REJECT_LABEL = "Not interested"


@dataclass(frozen=True)
class Callback:
    verdict: Verdict
    item_id: uuid.UUID


def callback_data(code: str, item_id: uuid.UUID) -> str:
    return f"{CALLBACK_PREFIX}:{code}:{item_id}"


def parse_callback(data: object) -> Callback | None:
    """Only well-formed ``de:a:<uuid>`` / ``de:r:<uuid>`` payloads are accepted."""
    if not isinstance(data, str):
        return None
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX or parts[1] not in CODE_TO_VERDICT:
        return None
    try:
        item_id = uuid.UUID(parts[2])
    except ValueError:
        return None
    return Callback(verdict=CODE_TO_VERDICT[parts[1]], item_id=item_id)


def _clip(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def title_of(content: dict[str, Any] | None) -> str:
    """The item headline, single line and capped. Never empty."""
    title = " ".join(_clip((content or {}).get("title"), MAX_TITLE_CHARS).split())
    return title or "New item"


def ping_text(
    content: dict[str, Any] | None, decision: dict[str, Any] | None, url: str | None
) -> str:
    """Short HTML message for an item waiting for approval."""
    title = title_of(content)
    rationale = _clip((decision or {}).get("rationale"), MAX_RATIONALE_CHARS)
    lines = [f"<b>{html.escape(title)}</b>"]
    if rationale:
        lines.append(html.escape(rationale))
    if url and url.startswith("https://"):
        lines.append(html.escape(url, quote=True))
    return "\n".join(lines)[:MAX_TEXT_CHARS]


def ping_keyboard(item_id: uuid.UUID) -> list[list[dict[str, str]]]:
    """One row: approve (uses the recommended option) and reject."""
    return [
        [
            {"text": APPROVE_LABEL, "callback_data": callback_data(CODE_APPROVE, item_id)},
            {"text": REJECT_LABEL, "callback_data": callback_data(CODE_REJECT, item_id)},
        ]
    ]


def chat_is_allowed(chat_id: object, allowed: list[str]) -> bool:
    """Only allow-listed chats may use the bot (CLAUDE.md rule 1). Fails closed when empty."""
    return bool(allowed) and str(chat_id) in allowed
