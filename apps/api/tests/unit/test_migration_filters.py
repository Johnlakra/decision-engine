"""include_object keeps LangGraph checkpoint tables out of autogenerate (ADR 0003, NFR-12)."""

from types import SimpleNamespace

import pytest

from app.db.migration_filters import include_object


@pytest.mark.parametrize(
    "name", ["checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"]
)
def test_checkpoint_tables_excluded(name: str) -> None:
    assert include_object(None, name, "table", True, None) is False


def test_checkpoint_indexes_excluded() -> None:
    obj = SimpleNamespace(table=SimpleNamespace(name="checkpoints"))
    assert include_object(obj, "checkpoints_thread_id_idx", "index", True, None) is False


def test_own_objects_included() -> None:
    assert include_object(None, "items", "table", True, None) is True
    obj = SimpleNamespace(table=SimpleNamespace(name="items"))
    assert include_object(obj, "ix_items_tenant_created", "index", True, None) is True
    assert include_object(None, "tenant_id", "column", True, None) is True
