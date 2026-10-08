"""C1 ingest schemas (FR-01, FR-06, FR-07)."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.ingest import BulkIn, Hints, IngestItemIn, IngestResult


def _body(**over: Any) -> dict[str, Any]:
    return {"source": "manual", "source_ref": "ref-1", "payload": {"a": 1}, **over}


def test_valid_minimal_item() -> None:
    item = IngestItemIn.model_validate(_body())
    assert item.hints is None
    assert item.callback_url is None


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        IngestItemIn.model_validate(_body(surprise=1))
    with pytest.raises(ValidationError):
        Hints.model_validate({"nope": 1})


@pytest.mark.parametrize("source", ["Manual", "1abc", "a", "has space", "x" * 41])
def test_rejects_bad_source(source: str) -> None:
    with pytest.raises(ValidationError):
        IngestItemIn.model_validate(_body(source=source))


@pytest.mark.parametrize("ref", ["", "x" * 301])
def test_rejects_bad_source_ref(ref: str) -> None:
    with pytest.raises(ValidationError):
        IngestItemIn.model_validate(_body(source_ref=ref))


@pytest.mark.parametrize("payload", [{"k": "v"}, [1, 2], "text"])
def test_payload_may_be_object_array_or_string(payload: Any) -> None:
    assert IngestItemIn.model_validate(_body(payload=payload)).payload == payload


def test_payload_number_rejected() -> None:
    with pytest.raises(ValidationError):
        IngestItemIn.model_validate(_body(payload=5))


def test_hints_sensitivity_enum_and_limits() -> None:
    assert Hints(sensitivity="public").sensitivity == "public"
    with pytest.raises(ValidationError):
        Hints(sensitivity="secret")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Hints(title="x" * 501)


def test_callback_url_must_be_https(settings_env: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert IngestItemIn.model_validate(_body(callback_url="https://x.io/cb")).callback_url
    for bad in ("http://x.io/cb", "ftp://x.io", "/relative", "https://" + "a" * 2000):
        with pytest.raises(ValidationError):
            IngestItemIn.model_validate(_body(callback_url=bad))


def test_http_callback_allowed_when_private_urls_allowed(
    settings_env: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings

    settings_env.setenv("WEBHOOK_ALLOW_PRIVATE_URLS", "true")
    get_settings.cache_clear()
    assert IngestItemIn.model_validate(_body(callback_url="http://localhost:9/cb")).callback_url


def test_bulk_limits() -> None:
    row = _body()
    assert len(BulkIn.model_validate({"items": [row]}).items) == 1
    with pytest.raises(ValidationError):
        BulkIn.model_validate({"items": [row] * 501})
    with pytest.raises(ValidationError):
        BulkIn.model_validate({"items": []})


def test_result_shape() -> None:
    assert IngestResult(id="abc", status="new").model_dump() == {"id": "abc", "status": "new"}
