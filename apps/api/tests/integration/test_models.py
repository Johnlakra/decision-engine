"""ORM behaviour against a real Postgres (FR-02, FR-06, FR-62)."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Item, Job, Tenant
from app.models.enums import ItemStatus
from app.models.item import EMBEDDING_DIM

pytestmark = pytest.mark.integration


def _item(tenant: Tenant, **overrides: object) -> Item:
    fields: dict[str, object] = {
        "tenant_id": tenant.id,
        "source": "email",
        "source_ref": "msg-1",
        "raw": {"subject": "hi"},
    }
    fields.update(overrides)
    return Item(**fields)


async def test_ids_are_uuid7(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    item = _item(tenant)
    db_session.add(item)
    await db_session.flush()
    assert isinstance(item.id, uuid.UUID)
    assert item.id.version == 7
    assert tenant.id.version == 7


async def test_defaults_and_nullable_embedding(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    item = _item(tenant)
    db_session.add(item)
    await db_session.flush()
    await db_session.refresh(item)
    assert item.status == ItemStatus.NEW
    assert item.embedding is None
    assert item.created_at.tzinfo is not None


async def test_duplicate_source_ref_rejected(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    db_session.add(_item(tenant))
    await db_session.flush()
    db_session.add(_item(tenant))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_status_rejected_by_check(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    db_session.add(_item(tenant, status="bogus"))
    with pytest.raises(IntegrityError, match="ck_items_status"):
        await db_session.flush()


async def test_invalid_job_status_rejected(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    db_session.add(Job(tenant_id=tenant.id, kind="process", status="nope"))
    with pytest.raises(IntegrityError, match="ck_jobs_status"):
        await db_session.flush()


async def test_vector_column_accepts_768_floats(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    vector = [0.001 * i for i in range(EMBEDDING_DIM)]
    item = _item(tenant, embedding=vector)
    db_session.add(item)
    await db_session.flush()
    await db_session.refresh(item)
    assert item.embedding is not None
    assert len(item.embedding) == EMBEDDING_DIM


async def test_vector_wrong_dimension_rejected(db_session, tenant: Tenant) -> None:  # type: ignore[no-untyped-def]
    db_session.add(_item(tenant, embedding=[0.1] * 10))
    with pytest.raises(Exception, match="768"):
        await db_session.flush()
