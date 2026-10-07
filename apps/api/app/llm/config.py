"""Load providers.yaml and overlay Settings (env) values: keys, models, budgets (FR-60, NFR-06)."""

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, SecretStr

from app.core.config import Settings, get_settings

YAML_PATH = Path(__file__).with_name("providers.yaml")
PRIVATE_CHAIN = "private"


class ProviderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    litellm_model: str = ""
    api_key: SecretStr | None = None
    needs_key: bool = False
    api_base: str | None = None
    needs_api_base: bool = False
    rpm: int | None = None
    rpd: int | None = None
    tpd: int | None = None
    private_ok: bool = False
    json_mode: Literal["native", "prompt"] = "prompt"
    purposes: tuple[str, ...] = ()
    price_in_inr_per_1m: float = 0.0
    price_out_inr_per_1m: float = 0.0

    @property
    def available(self) -> bool:
        """Has a model and its credential/URL (a missing key means the provider is skipped)."""
        if not self.litellm_model:
            return False
        if self.needs_key and not (self.api_key and self.api_key.get_secret_value()):
            return False
        return not (self.needs_api_base and not self.api_base)


class LLMConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    providers: dict[str, ProviderConfig]
    chains: dict[str, tuple[str, ...]]
    indic_languages: frozenset[str]
    indic_purposes: frozenset[str]
    max_tokens: dict[str, int]
    usd_inr: float

    def max_tokens_for(self, purpose: str) -> int:
        return self.max_tokens.get(purpose, self.max_tokens.get("default", 1000))


@lru_cache
def _raw_yaml() -> dict[str, Any]:
    with YAML_PATH.open(encoding="utf-8") as handle:
        return cast(dict[str, Any], yaml.safe_load(handle))


def _setting(settings: Settings, field: str | None, default: Any = None) -> Any:
    if not field:
        return default
    value = getattr(settings, field, None)
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return default if value in (None, "") else value


def _build_provider(name: str, raw: dict[str, Any], settings: Settings) -> ProviderConfig:
    key = _setting(settings, raw.get("key_env"), "")
    prices = raw.get("prices_inr_per_1m", {})
    return ProviderConfig(
        name=name,
        litellm_model=str(_setting(settings, raw.get("model_env"), raw.get("litellm_model", ""))),
        api_key=SecretStr(key) if key else None,
        needs_key=bool(raw.get("key_env")),
        api_base=_setting(settings, raw.get("api_base_env"), None),
        needs_api_base=bool(raw.get("api_base_env")),
        rpm=raw.get("rpm"),
        rpd=_setting(settings, raw.get("rpd_env"), raw.get("rpd")),
        tpd=raw.get("tpd"),
        private_ok=bool(
            _setting(settings, raw.get("private_ok_env"), raw.get("private_ok", False))
        ),
        json_mode=raw.get("json", "prompt"),
        purposes=tuple(raw.get("purposes", ())),
        price_in_inr_per_1m=float(prices.get("input", 0)),
        price_out_inr_per_1m=float(prices.get("output", 0)),
    )


def load_config(settings: Settings | None = None) -> LLMConfig:
    """Build the config from providers.yaml and the current settings (cheap, no caching)."""
    settings = settings or get_settings()
    raw = _raw_yaml()
    providers = {
        name: _build_provider(name, body, settings) for name, body in raw["providers"].items()
    }
    return LLMConfig(
        providers=providers,
        chains={name: tuple(members) for name, members in raw["chains"].items()},
        indic_languages=frozenset(raw["indic_languages"]),
        indic_purposes=frozenset(raw["indic_purposes"]),
        max_tokens=dict(raw["max_tokens"]),
        usd_inr=float(raw["usd_inr"]),
    )
