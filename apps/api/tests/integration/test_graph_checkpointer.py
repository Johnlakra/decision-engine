"""Checkpointer setup and round-trip (ADR 0003, NFR-03). Needs Postgres."""

import pytest

from app.graph.checkpointer import open_checkpointer
from app.graph.setup import CHECKPOINT_SETUP_LOCK_KEY, setup_checkpoint_tables
from tests.committed_fixtures import CHECKPOINT_SETUP_LOCK_KEY as FIXTURE_KEY

pytestmark = pytest.mark.integration


def test_lock_key_matches_fixture() -> None:
    assert CHECKPOINT_SETUP_LOCK_KEY == FIXTURE_KEY


async def test_setup_is_idempotent_and_saver_opens(checkpoint_db: str) -> None:
    await setup_checkpoint_tables(checkpoint_db)
    await setup_checkpoint_tables(checkpoint_db)
    async with open_checkpointer(checkpoint_db) as saver:
        assert await saver.aget_tuple({"configurable": {"thread_id": "none"}}) is None
