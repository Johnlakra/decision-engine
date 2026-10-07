"""API key format and hashing (FR-07, NFR-05)."""

import re

import pytest

from app.security.api_keys import Principal, generate_key, hash_secret, parse_key

PEPPER = "test-pepper"


def test_generated_key_has_documented_format() -> None:
    key = generate_key(PEPPER)
    assert re.fullmatch(r"de_[0-9a-f]{8}_[A-Za-z0-9_-]+", key.full)
    assert key.full.startswith(f"de_{key.prefix}_")


def test_hash_is_sha256_of_secret_plus_pepper_and_hides_secret() -> None:
    key = generate_key(PEPPER)
    parsed = parse_key(key.full)
    assert parsed is not None
    _, secret = parsed
    assert key.hash == hash_secret(secret, PEPPER)
    assert re.fullmatch(r"[0-9a-f]{64}", key.hash)
    assert secret not in key.hash
    assert hash_secret(secret, "other") != key.hash


def test_parse_keeps_underscores_in_secret() -> None:
    assert parse_key("de_0123abcd_se_cr_et") == ("0123abcd", "se_cr_et")


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "de",
        "de_0123abcd",
        "de_0123abcd_",
        "xx_0123abcd_s",
        "de_0123ABCD_s",
        "de_0123abc_s",
        "de_0123abcg_s",
    ],
)
def test_parse_rejects_malformed(raw: str) -> None:
    assert parse_key(raw) is None


def test_admin_implies_every_scope() -> None:
    import uuid

    admin = Principal(uuid.uuid4(), uuid.uuid4(), frozenset({"admin"}))
    reader = Principal(uuid.uuid4(), uuid.uuid4(), frozenset({"items:read"}))
    assert all(admin.allows(s) for s in ("items:write", "items:read", "decide", "admin"))
    assert reader.allows("items:read") and not reader.allows("decide")


def test_cli_rejects_unknown_scope_before_touching_the_db(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.security.api_keys import main

    assert main(["create", "--name", "x", "--scopes", "root"]) == 2
    assert "scopes" in capsys.readouterr().err
