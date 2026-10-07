"""Base fixtures: settings override, integration marker and skip logic."""

import os
import socket
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://de:de@localhost:5432/de_test"


def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _db_reachable(url: str) -> bool:
    parsed = urlparse(url)
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 1):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _db_reachable(test_database_url()):
        return
    skip = pytest.mark.skip(
        reason=(
            f"SKIPPING integration tests: Postgres at {test_database_url()} is unreachable. "
            "Start the db (docker compose up -d db) or set TEST_DATABASE_URL."
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Override environment variables for one test (Settings arrive in step 0.2)."""
    monkeypatch.setenv("APP_ENV", "test")
    yield monkeypatch
