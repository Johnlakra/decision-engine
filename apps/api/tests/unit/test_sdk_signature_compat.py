"""The SDK's verify_signature must agree with the server's signer (FR-96, FR-111)."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.security.hmac import sign

SIGNATURE_FILE = (
    Path(__file__).resolve().parents[4]
    / "packages/client-py/src/decision_engine_client/signature.py"
)
TS_FIXTURE = Path(__file__).resolve().parents[4] / "packages/client-ts/test/fixture.json"
SECRET = b"whsec_test_secret_placeholder"
BODY = b'{"event":"item.decided","id":"abc"}'
NOW = 1_800_000_000


def _load() -> ModuleType:
    # Load by path so the test needs no installed SDK and the SDK never imports `app`.
    spec = importlib.util.spec_from_file_location("sdk_signature", SIGNATURE_FILE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sdk = _load()


def test_accepts_server_signed_body() -> None:
    header = sign(SECRET, BODY, timestamp=NOW)
    sdk.verify_signature(SECRET, BODY, header, now=NOW)


def test_rejects_tampered_body() -> None:
    header = sign(SECRET, BODY, timestamp=NOW)
    with pytest.raises(sdk.InvalidSignature):
        sdk.verify_signature(SECRET, BODY + b" ", header, now=NOW)


def test_rejects_wrong_secret() -> None:
    header = sign(b"other", BODY, timestamp=NOW)
    with pytest.raises(sdk.InvalidSignature):
        sdk.verify_signature(SECRET, BODY, header, now=NOW)


def test_rejects_stale_timestamp() -> None:
    header = sign(SECRET, BODY, timestamp=NOW - 301)
    with pytest.raises(sdk.InvalidSignature):
        sdk.verify_signature(SECRET, BODY, header, now=NOW)


def test_tolerance_is_configurable() -> None:
    header = sign(SECRET, BODY, timestamp=NOW - 301)
    sdk.verify_signature(SECRET, BODY, header, now=NOW, tolerance_s=600)


@pytest.mark.parametrize("header", ["", "v1=abc", "t=1,v1=zz", f"t={NOW},v1={'A' * 64}"])
def test_rejects_malformed_header(header: str) -> None:
    with pytest.raises(sdk.InvalidSignature):
        sdk.verify_signature(SECRET, BODY, header, now=NOW)


def test_ts_fixture_matches_server_output() -> None:
    fixture = json.loads(TS_FIXTURE.read_text())
    assert fixture["header"] == sign(
        fixture["secret"].encode(), fixture["body"].encode(), timestamp=fixture["timestamp"]
    )
