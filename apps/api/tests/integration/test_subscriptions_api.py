"""/v1/subscriptions (FR-42)."""

import httpx
import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from tests.integration.graph_support import bearer

pytestmark = pytest.mark.integration

SECRET = "s3cret-s3cret-s3cret"
BODY = {"url": "https://example.com/hook", "events": ["decision.made"], "secret": SECRET}


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve any host to a public address so tests never touch the network."""
    monkeypatch.setenv("TOKEN_ENC_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.ssrf.resolve_host", lambda host: ["93.184.216.34"])


async def test_create_list_delete_never_returns_secret(
    api_client: httpx.AsyncClient, admin_key: str
) -> None:
    created = await api_client.post("/v1/subscriptions", json=BODY, headers=bearer(admin_key))
    assert created.status_code == 201
    assert SECRET not in created.text and "secret" not in created.json()
    sub_id = created.json()["id"]

    listed = await api_client.get("/v1/subscriptions", headers=bearer(admin_key))
    assert listed.status_code == 200
    assert [s["id"] for s in listed.json()["data"]] == [sub_id]
    assert SECRET not in listed.text and "secret_enc" not in listed.text

    gone = await api_client.delete(f"/v1/subscriptions/{sub_id}", headers=bearer(admin_key))
    assert gone.status_code == 204
    again = await api_client.delete(f"/v1/subscriptions/{sub_id}", headers=bearer(admin_key))
    assert again.status_code == 404
    listed = await api_client.get("/v1/subscriptions", headers=bearer(admin_key))
    assert listed.json()["data"] == []


async def test_loopback_url_is_422(api_client: httpx.AsyncClient, admin_key: str) -> None:
    body = {**BODY, "url": "http://127.0.0.1/hook"}
    response = await api_client.post("/v1/subscriptions", json=body, headers=bearer(admin_key))
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_loopback_url_allowed_with_flag(
    api_client: httpx.AsyncClient, admin_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    get_settings.cache_clear()
    body = {**BODY, "url": "http://127.0.0.1/hook"}
    response = await api_client.post("/v1/subscriptions", json=body, headers=bearer(admin_key))
    assert response.status_code == 201


@pytest.mark.parametrize(
    "patch", [{"events": ["nope"]}, {"events": []}, {"secret": "short"}], ids=str
)
async def test_invalid_input_is_422(
    api_client: httpx.AsyncClient, admin_key: str, patch: dict[str, object]
) -> None:
    response = await api_client.post(
        "/v1/subscriptions", json={**BODY, **patch}, headers=bearer(admin_key)
    )
    assert response.status_code == 422


async def test_requires_admin_scope(api_client: httpx.AsyncClient) -> None:
    assert (await api_client.get("/v1/subscriptions")).status_code == 401
