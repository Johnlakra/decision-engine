"""Webhook signing: header ``t=<unix>,v1=<hex>`` over ``"<t>." + body`` (NFR-05, FR-91)."""

import hashlib
import hmac
import re
import time

DEFAULT_TOLERANCE_S = 300
_HEADER = re.compile(r"^t=(\d+),v1=([0-9a-f]{64})$")


class InvalidSignature(Exception):  # noqa: N818 - public contract name
    """Signature header is malformed, stale or does not match."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _digest(secret: bytes, body: bytes, timestamp: int) -> str:
    return hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def sign(secret: bytes, body: bytes, *, timestamp: int | None = None) -> str:
    """Return the signature header for ``body``."""
    stamp = int(time.time()) if timestamp is None else timestamp
    return f"t={stamp},v1={_digest(secret, body, stamp)}"


def verify(
    secret: bytes,
    body: bytes,
    header: str,
    *,
    now: int | None = None,
    tolerance_s: int = DEFAULT_TOLERANCE_S,
) -> None:
    """Raise InvalidSignature unless ``header`` is a fresh, valid signature of ``body``."""
    match = _HEADER.fullmatch(header)
    if match is None:
        raise InvalidSignature("malformed signature header")
    stamp = int(match.group(1))
    current = int(time.time()) if now is None else now
    if abs(current - stamp) > tolerance_s:
        raise InvalidSignature("timestamp outside tolerance")
    if not hmac.compare_digest(_digest(secret, body, stamp), match.group(2)):
        raise InvalidSignature("signature mismatch")
