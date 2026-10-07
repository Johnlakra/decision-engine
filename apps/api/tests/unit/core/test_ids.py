"""ID and time helper tests (NFR-08)."""

import time
import uuid
from datetime import UTC

from app.core.ids import new_id
from app.core.time import TENANT_TZ, utcnow


def test_new_id_is_uuid7() -> None:
    value = new_id()
    assert isinstance(value, uuid.UUID) and value.version == 7


def test_ids_are_time_ordered() -> None:
    ids = []
    for _ in range(5):
        ids.append(new_id())
        time.sleep(0.002)
    assert ids == sorted(ids)
    assert len(set(ids)) == 5


def test_utcnow_is_aware_utc() -> None:
    assert utcnow().tzinfo is UTC or utcnow().utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_tenant_tz_default() -> None:
    assert str(TENANT_TZ) == "Asia/Kolkata"
