"""Verify ``X-DE-Signature: t=<unix>,v1=<hex>`` on webhook deliveries (stdlib only).

The signed payload is ``"<t>." + raw_body`` with HMAC-SHA-256. Must stay byte-compatible
with the server (checked by apps/api/tests/unit/test_sdk_signature_compat.py).
"""

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


def verify_signature(
    secret: bytes,
    body: bytes,
    header: str,
    *,
    tolerance_s: int = DEFAULT_TOLERANCE_S,
    now: int | None = None,
) -> None:
    """Raise InvalidSignature unless ``header`` is a fresh, valid signature of ``body``."""
    match = _HEADER.fullmatch(header)
    if match is None:
        raise InvalidSignature("malformed signature header")
    stamp = int(match.group(1))
    current = int(time.time()) if now is None else now
    if abs(current - stamp) > tolerance_s:
        raise InvalidSignature("timestamp outside tolerance")
    expected = hmac.new(secret, f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, match.group(2)):
        raise InvalidSignature("signature mismatch")
