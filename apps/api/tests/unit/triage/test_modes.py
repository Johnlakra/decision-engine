"""Mode resolution (FR-23, FR-24)."""

from app.triage.modes import has_active_override, resolve_mode


def test_defaults_to_shadow() -> None:
    assert resolve_mode({}, None, "shadow") == "shadow"


def test_garbage_default_still_shadow() -> None:
    assert resolve_mode({}, None, "garbage") == "shadow"


def test_tenant_beats_env() -> None:
    assert resolve_mode({"laya_mode": "off"}, None, "shadow") == "off"


def test_niche_override_beats_tenant() -> None:
    settings = {"laya_mode": "shadow", "laya_mode_by_niche": {"inbox": "on"}}
    assert resolve_mode(settings, "inbox", "shadow") == "on"
    assert resolve_mode(settings, "news_radar", "shadow") == "shadow"
    assert resolve_mode(settings, None, "shadow") == "shadow"


def test_invalid_values_are_ignored() -> None:
    settings = {"laya_mode": "turbo", "laya_mode_by_niche": {"inbox": 3}}
    assert resolve_mode(settings, "inbox", "off") == "off"


def test_has_active_override() -> None:
    assert not has_active_override({})
    assert not has_active_override({"laya_mode_by_niche": {"a": "off"}})
    assert has_active_override({"laya_mode_by_niche": {"a": "on"}})
