"""demo_item script and api_keys CLI against a scratch database (FR-07, NFR-05, NFR-08, A4).

A scratch database is used because both entry points pick "the default tenant" globally, which
must not depend on rows left behind by other tests.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command
from app.db import session as session_mod
from app.models import ApiKey, Item, Job, Tenant
from scripts import demo_item
from tests import conftest as base

pytestmark = pytest.mark.integration

API_ROOT = Path(__file__).resolve().parents[2]


def _admin_dsn() -> str:
    return base.test_database_url().replace("postgresql+asyncpg://", "postgresql://", 1)


def _scratch_url(name: str) -> str:
    parsed = urlparse(base.test_database_url())
    return parsed._replace(path=f"/{name}").geturl()


async def _admin(sql: str) -> None:
    conn = await asyncpg.connect(_admin_dsn())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


@pytest.fixture
def scratch_url() -> Iterator[str]:
    name = f"de_scratch_{uuid.uuid4().hex[:8]}"
    asyncio.run(_admin(f'CREATE DATABASE "{name}"'))
    url = _scratch_url(name)
    try:
        config = base.alembic_config()
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        yield url
    finally:
        asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest_asyncio.fixture
async def scratch_engine(
    scratch_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(scratch_url)
    monkeypatch.setattr(session_mod, "get_engine", lambda: engine)
    yield engine
    await engine.dispose()


def _run_module(module: str, scratch_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": scratch_url,
        "APP_ENV": "test",
        "API_KEY_PEPPER": "cli-test-pepper",
    }
    return subprocess.run(  # noqa: S603 - fixed argv, test only
        [sys.executable, "-m", module, *args],
        cwd=API_ROOT, env=env, capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip


async def _count(engine: AsyncEngine, model: type) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(select(func.count()).select_from(model)) or 0)


# --- scripts/demo_item.py (A4) ---


async def test_create_demo_item_inserts_item_and_process_job_together(
    scratch_engine: AsyncEngine,
) -> None:
    item_id = await demo_item.create_demo_item()
    async with scratch_engine.connect() as conn:
        item = (await conn.execute(text("select source, source_ref, status from items"))).one()
        job = (await conn.execute(text("select kind, status, item_id from jobs"))).one()
    assert uuid.UUID(item_id)
    assert item.source == "manual" and item.source_ref.startswith("demo-")
    assert item.status == "new"
    assert (job.kind, job.status, str(job.item_id)) == ("process", "queued", item_id)


async def test_demo_items_get_unique_source_refs_and_share_one_default_tenant(
    scratch_engine: AsyncEngine,
) -> None:
    first = await demo_item.create_demo_item()
    second = await demo_item.create_demo_item()
    assert first != second
    async with scratch_engine.connect() as conn:
        refs = [r[0] for r in await conn.execute(text("select source_ref from items"))]
    assert len(set(refs)) == 2
    assert await _count(scratch_engine, Tenant) == 1
    assert await _count(scratch_engine, Job) == 2


async def test_demo_item_rolls_back_item_when_enqueue_fails(
    scratch_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A4 contract: item + job are written in one transaction."""

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(demo_item, "enqueue", boom)
    with pytest.raises(RuntimeError):
        await demo_item.create_demo_item()
    assert await _count(scratch_engine, Item) == 0
    assert await _count(scratch_engine, Job) == 0


async def test_demo_item_script_prints_only_the_id(scratch_url: str) -> None:
    result = await asyncio.to_thread(_run_module, "scripts.demo_item", scratch_url)
    assert result.returncode == 0, result.stderr
    assert uuid.UUID(result.stdout.strip())
    assert len(result.stdout.strip().splitlines()) == 1


# --- python -m app.security.api_keys create ---


async def test_cli_create_makes_default_tenant_once_and_prints_key_once(
    scratch_url: str,
) -> None:
    first = await asyncio.to_thread(
        _run_module, "app.security.api_keys", scratch_url, "create", "--name", "k1"
    )
    second = await asyncio.to_thread(
        _run_module, "app.security.api_keys", scratch_url, "create", "--name", "k2"
    )
    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    key1, key2 = first.stdout.strip(), second.stdout.strip()
    assert key1.startswith("de_") and key2.startswith("de_") and key1 != key2
    assert len(first.stdout.strip().splitlines()) == 1  # printed exactly once, alone on stdout
    assert key1 not in first.stderr and "cannot be shown again" in first.stderr
    engine = create_async_engine(scratch_url)
    try:
        assert await _count(engine, Tenant) == 1
        async with engine.connect() as conn:
            rows = (await conn.execute(select(ApiKey.hash, ApiKey.scopes, ApiKey.name))).all()
    finally:
        await engine.dispose()
    assert sorted(r.name for r in rows) == ["k1", "k2"]
    assert all(r.scopes == ["admin"] for r in rows)
    assert all(key1 not in r.hash and key2 not in r.hash for r in rows)  # only hashes stored


async def test_cli_rejects_unknown_scope_with_exit_2_and_creates_nothing(
    scratch_url: str,
) -> None:
    result = await asyncio.to_thread(
        _run_module, "app.security.api_keys", scratch_url,
        "create", "--name", "bad", "--scopes", "items:read,root",
    )  # fmt: skip
    assert result.returncode == 2
    assert result.stdout == ""
    engine = create_async_engine(scratch_url)
    try:
        assert await _count(engine, ApiKey) == 0
        assert await _count(engine, Tenant) == 0
    finally:
        await engine.dispose()


async def test_cli_scopes_are_split_and_stored(scratch_url: str) -> None:
    result = await asyncio.to_thread(
        _run_module, "app.security.api_keys", scratch_url,
        "create", "--name", "rw", "--scopes", "items:read, items:write",
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    engine = create_async_engine(scratch_url)
    try:
        async with engine.connect() as conn:
            scopes = await conn.scalar(select(ApiKey.scopes))
    finally:
        await engine.dispose()
    assert scopes == ["items:read", "items:write"]
