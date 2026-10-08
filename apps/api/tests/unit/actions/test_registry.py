"""Action registry: registration, idempotency key, params validation (FR-40, FR-41, NFR-07)."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel, ValidationError

from app import actions  # noqa: F401  (registers the generic actions)
from app.actions import generic, registry
from app.actions.registry import ActionContext, ActionResult, idem_key, registered, run_action

ITEM = uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_generic_actions_registered_and_no_unsafe_ones() -> None:
    assert {"archive", "label", "snooze", "remind", "create_task", "webhook"} <= registered()
    assert not ({"notify", "draft_reply", "send_reply"} & registered())


def test_idem_key_is_sha256_of_item_action_canonical_params() -> None:
    expected = hashlib.sha256(f'{ITEM}|label|{{"a":1,"b":2}}'.encode()).hexdigest()
    assert idem_key(ITEM, "label", {"b": 2, "a": 1}) == expected


def test_idem_key_differs_by_params_and_action() -> None:
    assert idem_key(ITEM, "label", {"label": "a"}) != idem_key(ITEM, "label", {"label": "b"})
    assert idem_key(ITEM, "label", {}) != idem_key(ITEM, "archive", {})


def test_reversible_flags() -> None:
    assert registry.get("archive").reversible
    assert registry.get("label").reversible
    assert not registry.get("remind").reversible


@pytest.mark.parametrize("name", sorted(registry.names()))
def test_params_models_forbid_extra_and_have_no_url_or_email_fields(name: str) -> None:
    model = registry.get(name).params
    assert model.model_config.get("extra") == "forbid"
    for field in model.model_fields:
        assert "url" not in field.lower() and "email" not in field.lower()


def test_label_limits() -> None:
    generic.LabelParams(label="x" * 40)
    with pytest.raises(ValidationError):
        generic.LabelParams(label="x" * 41)
    with pytest.raises(ValidationError):
        generic.LabelParams(label="")
    with pytest.raises(ValidationError):
        generic.LabelParams(label="ok", url="https://evil.test")  # type: ignore[call-arg]


def test_remind_requires_aware_datetime() -> None:
    generic.RemindParams(until=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(ValidationError):
        generic.RemindParams(until=datetime(2030, 1, 1))  # naive


async def test_unknown_action_needs_no_db() -> None:
    ctx = ActionContext(session=None, tenant_id=uuid.uuid4(), item_id=ITEM, option_id="A")  # type: ignore[arg-type]
    result = await run_action(ctx, "rm_rf", {})
    assert result == ActionResult(ok=False, data={}, error="unknown_action")


def test_duplicate_registration_rejected() -> None:
    class P(BaseModel):
        pass

    with pytest.raises(ValueError):
        registry.action("archive", params=P)(lambda ctx, p: None)  # type: ignore[arg-type,return-value]
