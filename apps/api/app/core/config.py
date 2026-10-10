"""Application settings: every env var in /.env.example, with a default (NFR-05)."""

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
PLACEHOLDER_PREFIX = "change-me"
logger = logging.getLogger(__name__)
_HOURS = re.compile(r"^(\d{1,2})-(\d{1,2})$")


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


_DIR_DEFAULTS = {"niches_dir": "niches", "schemas_dir": "schemas", "data_dir": "data"}
CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Core
    app_env: Literal["dev", "test", "staging", "prod"] = "dev"  # runtime environment
    app_base_url: str = "http://localhost:8000"  # public API URL
    web_base_url: str = "http://localhost:3000"  # web app URL
    tenant_timezone: str = "Asia/Kolkata"  # IANA tz for tenant-facing times
    log_level: str = "INFO"  # stdlib log level
    cors_allow_origins: CsvList = ["http://localhost:3000"]  # comma-separated origins
    niches_dir: Path = REPO_ROOT / "niches"  # niche YAML directory (empty = default)
    schemas_dir: Path = REPO_ROOT / "schemas"  # JSON schema directory (empty = default)

    data_dir: Path = REPO_ROOT / "data"  # uploads, exports, eval sets (empty = default)
    items_per_day: int = 5000  # per-tenant cap on new items per UTC day (ADR 0004)
    decide_daily_limit_per_tenant: int = 500  # per-tenant POST /v1/decide calls per UTC day (429)
    max_request_bytes: int = 1_048_576  # max request body in bytes (413 above)
    max_bulk_request_bytes: int = 10_485_760  # max body for POST /v1/items/bulk (413 above)

    # Database / cache
    database_url: str = "postgresql+asyncpg://de:de@db:5432/de"  # async SQLAlchemy URL
    test_database_url: str = "postgresql+asyncpg://de:de@localhost:5432/de_test"  # tests only
    redis_url: str = "redis://redis:6379/0"  # empty = Redis off, Postgres fallback
    worker_active_hours: Annotated[tuple[int, int], NoDecode] = (0, 24)  # env "7-23": hour window
    worker_idle_poll_seconds: int = 30  # adaptive poll ceiling when idle
    worker_batch_size: int = 32  # jobs claimed per poll

    # Security
    api_key_pepper: SecretStr = SecretStr("change-me-long-random")  # API key hash pepper
    token_enc_key: SecretStr = SecretStr("")  # Fernet key for stored tokens
    allowed_emails: CsvList = []  # comma-separated Google accounts allowed to sign in
    auth_secret: SecretStr = SecretStr("")  # Auth.js secret (web)
    auth_google_id: str = ""  # Google sign-in client id
    auth_google_secret: SecretStr = SecretStr("")  # Google sign-in client secret
    rate_limit_per_min: int = 120  # per-key requests per minute
    webhook_allow_private_urls: bool = False  # dev only: allow http/private hosts
    webhook_timeout_seconds: float = 10  # per-delivery HTTP timeout
    decide_timeout_seconds: float = 30  # POST /v1/decide synchronous budget
    raw_retention_days: int = 180  # raw payload retention
    audio_retention_days: int = 7  # voice note retention

    # Laya
    laya_url: str = "http://laya:8000"  # empty = Laya off
    laya_api_key: SecretStr = SecretStr("change-me-long-random")  # shared with laya service
    laya_mode: Literal["off", "shadow", "on"] = "shadow"  # default triage mode
    laya_timeout_seconds: float = 10  # per-call timeout
    laya_model: str = ""  # empty = server auto-routing

    # LLM providers (empty key = provider skipped)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini/gemini-flash-lite-latest"
    gemini_rpd: int = 500  # requests per day budget
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "groq/openai/gpt-oss-120b"
    groq_rpd: int = 1000
    cerebras_api_key: SecretStr = SecretStr("")
    cerebras_model: str = "cerebras/gpt-oss-120b"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""
    openrouter_rpd: int = 50
    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_daily_inr: float = 20  # INR budget per day
    ollama_url: str = ""  # local LLM for private items
    ollama_model: str = "ollama_chat/qwen3:8b"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_private_ok: bool = False  # paid plan terms allow private items

    # Connectors
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_allowed_chat_ids: CsvList = []
    telegram_webhook_secret: SecretStr = SecretStr("")
    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr = SecretStr("")
    meta_app_id: str = ""
    meta_app_secret: SecretStr = SecretStr("")
    meta_verify_token: SecretStr = SecretStr("")
    data_gov_in_api_key: SecretStr = SecretStr("")
    expo_access_token: SecretStr = SecretStr("")

    @field_validator(
        "cors_allow_origins", "allowed_emails", "telegram_allowed_chat_ids", mode="before"
    )
    @classmethod
    def _csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("niches_dir", "schemas_dir", "data_dir", mode="before")
    @classmethod
    def _empty_dir_is_default(cls, value: object, info: object) -> object:
        if value in ("", None):
            name = getattr(info, "field_name", "")
            return REPO_ROOT / _DIR_DEFAULTS[name]
        return value

    @field_validator("worker_active_hours", mode="before")
    @classmethod
    def _hours(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        match = _HOURS.match(value.strip())
        if not match:
            raise ValueError("WORKER_ACTIVE_HOURS must look like 7-23")
        return (int(match[1]), int(match[2]))

    @model_validator(mode="after")
    def _hours_range(self) -> "Settings":
        start, end = self.worker_active_hours
        if not (0 <= start < end <= 24):
            raise ValueError("WORKER_ACTIVE_HOURS must satisfy 0 <= start < end <= 24")
        return self

    @model_validator(mode="after")
    def _pooler_warning(self) -> "Settings":
        host = urlparse(self.database_url).hostname or ""
        if "-pooler" in host:
            logger.warning(
                "DATABASE_URL points at a pooled endpoint (%s). The app needs LISTEN, session "
                "advisory locks and CREATE INDEX CONCURRENTLY: use the direct host (ADR 0003).",
                host,
            )
        return self

    @model_validator(mode="after")
    def _prod_private_urls(self) -> "Settings":
        if self.app_env == "prod" and self.webhook_allow_private_urls:
            raise ValueError("WEBHOOK_ALLOW_PRIVATE_URLS must be false when APP_ENV=prod")
        return self

    @property
    def db_pooler(self) -> bool:
        return "-pooler" in (urlparse(self.database_url).hostname or "")

    @model_validator(mode="after")
    def _prod_secrets(self) -> "Settings":
        if self.app_env != "prod":
            return self
        required = {"API_KEY_PEPPER": self.api_key_pepper, "TOKEN_ENC_KEY": self.token_enc_key}
        if self.laya_enabled:
            required["LAYA_API_KEY"] = self.laya_api_key
        bad = [
            name
            for name, secret in required.items()
            if not secret.get_secret_value()
            or secret.get_secret_value().startswith(PLACEHOLDER_PREFIX)
        ]
        if bad:
            raise ValueError(f"APP_ENV=prod requires real values for: {', '.join(bad)}")
        return self

    @property
    def redis_enabled(self) -> bool:
        return bool(self.redis_url.strip())

    @property
    def laya_enabled(self) -> bool:
        return bool(self.laya_url.strip()) and self.laya_mode != "off"


@lru_cache
def get_settings() -> Settings:
    return Settings()
