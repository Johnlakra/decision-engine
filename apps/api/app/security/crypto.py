"""Fernet encryption for stored tokens (NFR-07). Fails closed when no key is set."""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


class CryptoNotConfigured(Exception):  # noqa: N818 - public contract name
    """TOKEN_ENC_KEY is empty or not a valid Fernet key."""


class DecryptError(Exception):
    """Token is corrupt, tampered with, or encrypted under another key."""


def _fernet(key: str | None) -> Fernet:
    raw = get_settings().token_enc_key.get_secret_value() if key is None else key
    if not raw:
        raise CryptoNotConfigured("TOKEN_ENC_KEY is not set")
    try:
        return Fernet(raw.encode())
    except ValueError as exc:
        raise CryptoNotConfigured("TOKEN_ENC_KEY is not a valid Fernet key") from exc


def encrypt(plaintext: str, *, key: str | None = None) -> str:
    return _fernet(key).encrypt(plaintext.encode()).decode()


def decrypt(token: str, *, key: str | None = None) -> str:
    try:
        return _fernet(key).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise DecryptError("could not decrypt token") from exc
