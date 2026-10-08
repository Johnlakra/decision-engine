"""committed_db / api_client / admin_key fixtures work end to end (FR-07, NFR-12)."""

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ApiKey

pytestmark = pytest.mark.integration


async def test_admin_key_authenticates_and_data_is_committed(
    api_client: httpx.AsyncClient,
    admin_key: str,
    committed_db: async_sessionmaker[AsyncSession],
) -> None:
    assert (await api_client.get("/health")).status_code == 200
    async with committed_db() as session:
        assert await session.scalar(select(func.count()).select_from(ApiKey)) == 1
    assert admin_key.startswith("de_")


async def test_tables_are_emptied_between_tests(
    committed_db: async_sessionmaker[AsyncSession],
) -> None:
    async with committed_db() as session:
        assert await session.scalar(select(func.count()).select_from(ApiKey)) == 0
        assert await session.scalar(text("SELECT count(*) FROM checkpoints")) == 0
