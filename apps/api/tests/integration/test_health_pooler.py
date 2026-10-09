"""/health/deep reports whether DATABASE_URL points at a pooler (ADR 0003, NFR-08)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Tenant
from tests.integration.test_health import _headers, client  # noqa: F401

pytestmark = pytest.mark.integration


async def test_deep_reports_db_pooler_flag(
    client: httpx.AsyncClient,  # noqa: F811
    db_session: AsyncSession,
    tenant: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _headers(db_session, tenant)
    assert (await client.get("/health/deep", headers=headers)).json()["db_pooler"] is False

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@ep-x-pooler.neon.tech/de")
    get_settings.cache_clear()
    try:
        assert (await client.get("/health/deep", headers=headers)).json()["db_pooler"] is True
    finally:
        get_settings.cache_clear()
