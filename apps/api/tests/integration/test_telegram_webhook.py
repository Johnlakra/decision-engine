"""Telegram webhook over the ASGI app: secret check, allow-list, forwarded text (FR-94, FR-07)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import Item
from app.models.enums import ItemStatus

pytestmark = pytest.mark.integration

SECRET = "telegram-test-secret"
OWNER_CHAT = 111
STRANGER_CHAT = 999
WEBHOOK = "/v1/telegram/webhook"
SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


@pytest_asyncio.fixture
async def telegram_settings(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", str(OWNER_CHAT))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def forwarded(chat_id: int, message_id: int, text: str) -> dict[str, object]:
    return {
        "update_id": message_id,
        "message": {"message_id": message_id, "chat": {"id": chat_id}, "text": text},
    }


async def telegram_items(factory: async_sessionmaker[AsyncSession]) -> list[Item]:
    async with factory() as session:
        stmt = select(Item).where(Item.source == "telegram")
        return list((await session.execute(stmt)).scalars().all())


async def test_webhook_rejects_a_missing_or_wrong_secret(
    api_client: httpx.AsyncClient, telegram_settings: None
) -> None:
    body = forwarded(OWNER_CHAT, 1, "hello")

    missing = await api_client.post(WEBHOOK, json=body)
    wrong = await api_client.post(
        WEBHOOK, json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "nope"}
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403


async def test_forwarded_text_from_the_owner_becomes_a_private_item(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    telegram_settings: None,
) -> None:
    body = forwarded(OWNER_CHAT, 7, "Free credits\nApply before 30 Nov")

    response = await api_client.post(WEBHOOK, json=body, headers=SECRET_HEADER)

    assert response.status_code == 200
    (item,) = await telegram_items(committed_db)
    assert item.source_ref == f"{OWNER_CHAT}:7"
    assert item.sensitivity == "private"  # telegram defaults to private (ADR 0005)
    assert item.status == ItemStatus.NEW.value
    assert item.hints is not None and item.hints["title"] == "Free credits"


async def test_messages_from_unknown_chats_are_ignored(
    api_client: httpx.AsyncClient,
    committed_db: async_sessionmaker[AsyncSession],
    telegram_settings: None,
) -> None:
    response = await api_client.post(
        WEBHOOK, json=forwarded(STRANGER_CHAT, 8, "spam"), headers=SECRET_HEADER
    )

    assert response.status_code == 200
    assert await telegram_items(committed_db) == []


async def test_a_button_for_an_unknown_item_does_not_fail_the_update(
    api_client: httpx.AsyncClient, telegram_settings: None
) -> None:
    update = {
        "update_id": 9,
        "callback_query": {
            "id": "cb-1",
            "data": f"de:a:{uuid.uuid4()}",
            "message": {"message_id": 3, "chat": {"id": OWNER_CHAT}},
        },
    }

    response = await api_client.post(WEBHOOK, json=update, headers=SECRET_HEADER)

    # No bot token is configured in tests, so the toast is logged and skipped; the update is 200.
    assert response.status_code == 200


async def test_non_json_body_is_a_bad_request(
    api_client: httpx.AsyncClient, telegram_settings: None
) -> None:
    response = await api_client.post(
        WEBHOOK,
        content=b"not json",
        headers={**SECRET_HEADER, "Content-Type": "application/json"},
    )

    assert response.status_code == 400
