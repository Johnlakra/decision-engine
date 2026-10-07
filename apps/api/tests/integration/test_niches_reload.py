"""POST /v1/niches/reload (FR-70, FR-71)."""

import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_rate_limiter
from app.core.config import REPO_ROOT, get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import Tenant
from app.niches import registry as registry_mod
from app.security.api_keys import create_api_key
from app.security.rate_limit import MemoryRateLimiter

pytestmark = pytest.mark.integration


@pytest.fixture
def niches_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "niches"
    shutil.copytree(REPO_ROOT / "niches", target)
    monkeypatch.setenv("NICHES_DIR", str(target))
    get_settings.cache_clear()
    monkeypatch.setattr(registry_mod, "_registry", None)
    return target


@pytest_asyncio.fixture
async def client(niches_dir: Path, db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    limiter = MemoryRateLimiter()
    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as http:
        yield http
    get_settings.cache_clear()


async def _headers(session: AsyncSession, tenant: Tenant, scopes: list[str]) -> dict[str, str]:
    pepper = get_settings().api_key_pepper.get_secret_value()
    return {
        "Authorization": f"Bearer {await create_api_key(session, tenant.id, 't', scopes, pepper)}"
    }


async def test_reload_requires_key(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/niches/reload")).status_code == 401


async def test_reload_non_admin_is_403(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _headers(db_session, tenant, ["items:write"])
    assert (await client.post("/v1/niches/reload", headers=headers)).status_code == 403


async def test_valid_reload_lists_five_niches(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant
) -> None:
    headers = await _headers(db_session, tenant, ["admin"])
    resp = await client.post("/v1/niches/reload", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "loaded": ["agriculture", "generic", "inbox", "news_radar", "tech_stack"],
        "errors": [],
    }


async def test_invalid_file_is_422_and_previous_set_kept(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant, niches_dir: Path
) -> None:
    headers = await _headers(db_session, tenant, ["admin"])
    assert (await client.post("/v1/niches/reload", headers=headers)).status_code == 200
    (niches_dir / "inbox.yaml").write_text("name: inbox\nautonomy: [not valid\n")
    resp = await client.post("/v1/niches/reload", headers=headers)
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith("application/problem+json")
    err = resp.json()["errors"][0]
    assert set(err) == {"file", "json_pointer", "message"} and "inbox" in err["file"]
    assert "inbox" in {n.name for n in registry_mod.get_registry().all()}


async def test_missing_generic_on_first_load_is_422(
    client: httpx.AsyncClient, db_session: AsyncSession, tenant: Tenant, niches_dir: Path
) -> None:
    headers = await _headers(db_session, tenant, ["admin"])
    (niches_dir / "generic.yaml").unlink()
    # Fresh empty registry that never loaded generic.
    registry_mod._registry = registry_mod.NicheRegistry(niches_dir, get_settings().schemas_dir)
    resp = await client.post("/v1/niches/reload", headers=headers)
    assert resp.status_code == 422
