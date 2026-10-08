"""Settings tests (NFR-05)."""

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

REPO = Path(__file__).resolve().parents[5]
ENV_VAR = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def make(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VAR.findall((REPO / ".env.example").read_text()):
        monkeypatch.delenv(name, raising=False)


def test_every_env_example_var_maps_to_a_field() -> None:
    """NFR-05: every documented env var is a Settings field."""
    names = ENV_VAR.findall((REPO / ".env.example").read_text())
    assert names
    missing = [n for n in names if n.lower() not in Settings.model_fields]
    assert missing == []


def test_defaults_and_derived() -> None:
    s = make()
    assert s.worker_active_hours == (0, 24)
    assert s.redis_enabled and s.laya_enabled
    assert s.niches_dir == REPO / "niches"
    assert s.schemas_dir == REPO / "schemas"


def test_empty_urls_disable_features(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "")
    monkeypatch.setenv("LAYA_URL", "")
    monkeypatch.setenv("NICHES_DIR", "")
    s = make()
    assert not s.redis_enabled and not s.laya_enabled
    assert s.niches_dir == REPO / "niches"


def test_worker_hours_parsed() -> None:
    assert make(WORKER_ACTIVE_HOURS="7-23").worker_active_hours == (7, 23)
    with pytest.raises(ValidationError):
        make(WORKER_ACTIVE_HOURS="nonsense")


def test_secrets_are_not_printed() -> None:
    assert "s3cret" not in repr(make(API_KEY_PEPPER="s3cret"))


@pytest.mark.parametrize(
    "env",
    [
        {"API_KEY_PEPPER": "", "TOKEN_ENC_KEY": "k", "LAYA_API_KEY": "x"},
        {"API_KEY_PEPPER": "change-me-long-random", "TOKEN_ENC_KEY": "k", "LAYA_API_KEY": "x"},
        {"API_KEY_PEPPER": "p", "TOKEN_ENC_KEY": "", "LAYA_API_KEY": "x"},
        {"API_KEY_PEPPER": "p", "TOKEN_ENC_KEY": "k", "LAYA_API_KEY": "change-me-long-random"},
        {"API_KEY_PEPPER": "p", "TOKEN_ENC_KEY": "k", "LAYA_API_KEY": ""},
    ],
)
def test_prod_rejects_placeholders(env: dict[str, str]) -> None:
    """NFR-05: prod refuses to start with placeholder secrets."""
    with pytest.raises(ValidationError):
        make(APP_ENV="prod", **env)


def test_prod_ok_and_laya_key_optional_when_laya_off() -> None:
    make(APP_ENV="prod", API_KEY_PEPPER="p", TOKEN_ENC_KEY="k", LAYA_API_KEY="x")
    make(APP_ENV="prod", API_KEY_PEPPER="p", TOKEN_ENC_KEY="k", LAYA_URL="", LAYA_API_KEY="")


def test_dev_allows_placeholders() -> None:
    make(APP_ENV="dev", API_KEY_PEPPER="change-me")


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()


def test_phase1_defaults() -> None:
    """FR-07 (ADR 0004): per-tenant cap and webhook knobs have safe defaults."""
    s = make()
    assert s.items_per_day == 5000
    assert s.webhook_allow_private_urls is False
    assert s.webhook_timeout_seconds == 10
    assert s.decide_timeout_seconds == 30
    assert s.data_dir == REPO / "data"
    assert make(DATA_DIR="").data_dir == REPO / "data"


def test_prod_rejects_private_webhook_urls() -> None:
    secrets = {"API_KEY_PEPPER": "real-pepper", "TOKEN_ENC_KEY": "k", "LAYA_API_KEY": "real"}
    with pytest.raises(ValidationError, match="WEBHOOK_ALLOW_PRIVATE_URLS"):
        make(APP_ENV="prod", WEBHOOK_ALLOW_PRIVATE_URLS="true", **secrets)
    assert make(APP_ENV="prod", **secrets).webhook_allow_private_urls is False


def test_pooler_url_warns(caplog: pytest.LogCaptureFixture) -> None:
    """ADR 0003: pooled endpoints break LISTEN and advisory locks."""
    url = "postgresql+asyncpg://u:p@ep-x-pooler.neon.tech/de"
    with caplog.at_level("WARNING"):
        s = make(DATABASE_URL=url)
    assert s.db_pooler is True
    assert "pooled endpoint" in caplog.text
    assert make().db_pooler is False
