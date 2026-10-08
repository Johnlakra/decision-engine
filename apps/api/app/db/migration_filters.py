"""Alembic autogenerate filters (ADR 0003)."""

# LangGraph's AsyncPostgresSaver.setup() owns these tables; Alembic must never touch them.
CHECKPOINT_TABLES = frozenset(
    {"checkpoint_migrations", "checkpoints", "checkpoint_blobs", "checkpoint_writes"}
)


def include_object(
    obj: object, name: str | None, type_: str, reflected: bool, compare_to: object
) -> bool:
    """Return False for checkpoint tables and their indexes so autogenerate ignores them."""
    if type_ == "table":
        return name not in CHECKPOINT_TABLES
    if type_ == "index":
        table = getattr(obj, "table", None)
        if getattr(table, "name", None) in CHECKPOINT_TABLES:
            return False
        return not (name or "").startswith("checkpoint")
    return True
