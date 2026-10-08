"""Fixtures for the acceptance tests: committed data, real worker, ASGI client, Laya/LLM fakes.

Uses ``committed_db`` (A1, tests/conftest.py) for per-test truncation and checkpoint setup.
"""

import socket
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.session import get_engine
from app.models import Tenant
from app.models.tenant_settings import TenantSettings
from app.security.api_keys import create_api_key
from tests.conftest import test_database_url
from tests.fakes.fake_llm import FakeLLM

from ._scripts import install_llm


@dataclass(frozen=True)
class Account:
    tenant_id: Any
    key: str


@pytest.fixture
def pipeline_env(
    settings_env: pytest.MonkeyPatch, committed_db: Any
) -> Iterator[pytest.MonkeyPatch]:
    """Point the app (graph nodes open their own sessions) at the test database."""
    settings_env.setenv("DATABASE_URL", test_database_url())
    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    settings_env.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())
    settings_env.setenv("LAYA_MODE", "shadow")
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield settings_env
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def factory(
    pipeline_env: pytest.MonkeyPatch,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(test_database_url())
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def account(factory: async_sessionmaker[AsyncSession]) -> Account:
    pepper = get_settings().api_key_pepper.get_secret_value()
    async with factory() as session:
        tenant = Tenant(name="Acceptance")
        session.add(tenant)
        await session.flush()
        key = await create_api_key(session, tenant.id, "acceptance", ["admin"], pepper)
        await session.commit()
    return Account(tenant.id, key)


@pytest.fixture
def llm(pipeline_env: pytest.MonkeyPatch) -> FakeLLM:
    return install_llm(FakeLLM(), pipeline_env)


@pytest.fixture
def use_laya(pipeline_env: pytest.MonkeyPatch) -> Callable[[Any], None]:
    """Make ``get_laya_client()`` return the given client everywhere it was imported."""

    def install(client: Any) -> None:
        import importlib

        for name in ("app.triage", "app.triage.service", "app.workers.pipeline"):
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            if hasattr(module, "get_laya_client"):
                pipeline_env.setattr(module, "get_laya_client", lambda: client)

    return install


@pytest_asyncio.fixture
async def set_laya_mode(
    factory: async_sessionmaker[AsyncSession], account: Account
) -> Callable[[str], Any]:
    async def apply(mode: str) -> None:
        async with factory() as session:
            session.add(TenantSettings(tenant_id=account.tenant_id, settings={"laya_mode": mode}))
            await session.commit()

    return apply


@pytest_asyncio.fixture
async def client(pipeline_env: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


def closed_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """P7 is a repo-text check: the directory name must not skip it when Postgres is down."""
    for item in items:
        if item.path.name == "test_p7_laya_never_on.py":
            item.own_markers = [m for m in item.own_markers if m.name != "skip"]
