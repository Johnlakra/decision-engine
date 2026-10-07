"""Tests for app.security.hmac sign/verify (NFR-05, FR-91)."""

import hashlib
import hmac as std_hmac
import re
import time

import pytest
from app.security.hmac import InvalidSignature, sign, verify

SECRET = b"s3cret-key-for-tests"
BODY = b'{"event":"item.created","id":"abc"}'
NOW = 1_800_000_000


def test_sign_format_and_digest() -> None:
    """FR-91: header is t=<unix>,v1=<hex> over '<t>.' + body."""
    header = sign(SECRET, BODY, timestamp=NOW)
    assert re.fullmatch(r"t=\d+,v1=[0-9a-f]{64}", header)
    expected = std_hmac.new(SECRET, f"{NOW}.".encode() + BODY, hashlib.sha256).hexdigest()
    assert header == f"t={NOW},v1={expected}"


def test_sign_defaults_to_current_time() -> None:
    """FR-91: timestamp defaults to now."""
    header = sign(SECRET, BODY)
    stamp = int(header.split(",")[0].removeprefix("t="))
    assert abs(stamp - time.time()) < 5


def test_round_trip() -> None:
    """FR-91: a signed body verifies."""
    header = sign(SECRET, BODY, timestamp=NOW)
    assert verify(SECRET, BODY, header, now=NOW) is None


def test_round_trip_default_now() -> None:
    """FR-91: verify without now uses the current clock."""
    verify(SECRET, BODY, sign(SECRET, BODY))


def test_tampered_body_fails() -> None:
    """FR-91: any body change invalidates the signature."""
    header = sign(SECRET, BODY, timestamp=NOW)
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY + b" ", header, now=NOW)


def test_wrong_secret_fails() -> None:
    """FR-91: a different secret fails."""
    header = sign(SECRET, BODY, timestamp=NOW)
    with pytest.raises(InvalidSignature):
        verify(b"other", BODY, header, now=NOW)


def test_tampered_timestamp_fails() -> None:
    """FR-91: the timestamp is covered by the MAC."""
    header = sign(SECRET, BODY, timestamp=NOW)
    forged = header.replace(f"t={NOW}", f"t={NOW + 1}")
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, forged, now=NOW)


@pytest.mark.parametrize("skew", [301, 3600, -301, -3600])
def test_skew_over_tolerance_fails(skew: int) -> None:
    """FR-91, NFR-05: skew > 300 s in either direction is rejected (replay)."""
    header = sign(SECRET, BODY, timestamp=NOW)
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, header, now=NOW + skew)


@pytest.mark.parametrize("skew", [0, 299, 300, -299, -300])
def test_skew_within_tolerance_passes(skew: int) -> None:
    """FR-91: skew up to 300 s is accepted."""
    header = sign(SECRET, BODY, timestamp=NOW)
    verify(SECRET, BODY, header, now=NOW + skew)


def test_custom_tolerance() -> None:
    """FR-91: tolerance_s is honored."""
    header = sign(SECRET, BODY, timestamp=NOW)
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, header, now=NOW + 20, tolerance_s=10)


@pytest.mark.parametrize(
    "header",
    [
        "",
        "garbage",
        f"t={NOW}",
        "v1=" + "a" * 64,
        f"t=abc,v1={'a' * 64}",
        f"t=,v1={'a' * 64}",
        f"t={NOW},v1=",
        f"t={NOW},v1=zzzz",
        f"t={NOW},v1={'g' * 64}",
        f"t={NOW},v2={'a' * 64}",
        f"t={NOW};v1={'a' * 64}",
    ],
)
def test_malformed_header_fails(header: str) -> None:
    """FR-91: malformed headers raise InvalidSignature, never another error."""
    with pytest.raises(InvalidSignature):
        verify(SECRET, BODY, header, now=NOW)


def test_invalid_signature_carries_reason() -> None:
    """FR-91: InvalidSignature(reason) exposes a reason string."""
    with pytest.raises(InvalidSignature) as info:
        verify(SECRET, BODY, "garbage", now=NOW)
    assert str(info.value)


def test_uses_constant_time_compare(monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-05: signature comparison goes through hmac.compare_digest."""
    calls: list[tuple[object, object]] = []
    real = std_hmac.compare_digest

    def spy(a: object, b: object) -> bool:
        calls.append((a, b))
        return real(a, b)  # type: ignore[arg-type]

    monkeypatch.setattr(std_hmac, "compare_digest", spy)
    header = sign(SECRET, BODY, timestamp=NOW)
    verify(SECRET, BODY, header, now=NOW)
    assert calls, "hmac.compare_digest was not called"
