"""Tests for app.security.crypto Fernet helpers (NFR-07)."""

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from app.core.config import get_settings
from app.security.crypto import (
    CryptoNotConfigured,
    DecryptError,
    decrypt,
    encrypt,
)

PLAINTEXT = "ya29.super-secret-oauth-refresh-token"


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_round_trip(key: str) -> None:
    """NFR-07: decrypt(encrypt(x)) == x."""
    assert decrypt(encrypt(PLAINTEXT, key=key), key=key) == PLAINTEXT


def test_round_trip_unicode(key: str) -> None:
    """NFR-07: non-ASCII plaintext survives."""
    text = "टोकन-ਟੋਕਨ-🔑"
    assert decrypt(encrypt(text, key=key), key=key) == text


def test_ciphertext_does_not_contain_plaintext(key: str) -> None:
    """NFR-07: the token never exposes the plaintext."""
    token = encrypt(PLAINTEXT, key=key)
    assert isinstance(token, str)
    assert PLAINTEXT not in token
    assert "super-secret" not in token


def test_encrypt_is_randomized(key: str) -> None:
    """NFR-07: Fernet tokens differ per call."""
    assert encrypt(PLAINTEXT, key=key) != encrypt(PLAINTEXT, key=key)


def test_wrong_key_raises_decrypt_error(key: str) -> None:
    """NFR-07: a different key cannot decrypt."""
    token = encrypt(PLAINTEXT, key=key)
    with pytest.raises(DecryptError):
        decrypt(token, key=Fernet.generate_key().decode())


def test_garbage_token_raises_decrypt_error(key: str) -> None:
    """NFR-07: a corrupt token is a DecryptError."""
    with pytest.raises(DecryptError):
        decrypt("not-a-fernet-token", key=key)


def test_tampered_token_raises_decrypt_error(key: str) -> None:
    """NFR-07: modified ciphertext is detected."""
    token = encrypt(PLAINTEXT, key=key)
    flipped = token[:-4] + ("AAAA" if token[-4:] != "AAAA" else "BBBB")
    with pytest.raises(DecryptError):
        decrypt(flipped, key=key)


def test_empty_key_raises_not_configured() -> None:
    """NFR-07: an empty key must fail closed, never store plaintext."""
    with pytest.raises(CryptoNotConfigured):
        encrypt(PLAINTEXT, key="")
    with pytest.raises(CryptoNotConfigured):
        decrypt("whatever", key="")


def test_unset_setting_raises_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-07: with no key argument and an empty TOKEN_ENC_KEY, fail closed."""
    monkeypatch.setenv("TOKEN_ENC_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(CryptoNotConfigured):
        encrypt(PLAINTEXT)


def test_key_defaults_to_setting(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    """NFR-07: the key defaults to the TOKEN_ENC_KEY setting."""
    monkeypatch.setenv("TOKEN_ENC_KEY", key)
    get_settings.cache_clear()
    token = encrypt(PLAINTEXT)
    assert decrypt(token) == PLAINTEXT
    assert decrypt(token, key=key) == PLAINTEXT
