"""Identifier helpers: UUIDv7 everywhere (time-ordered)."""

import uuid

from uuid6 import uuid7


def new_id() -> uuid.UUID:
    """Return a fresh UUIDv7."""
    return uuid.UUID(int=uuid7().int)
