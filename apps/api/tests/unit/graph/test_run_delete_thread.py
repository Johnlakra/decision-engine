"""Public delete_thread helper (FR-33, NFR-03)."""

import uuid
from collections.abc import Iterator

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.graph import run


@pytest.fixture(autouse=True)
def _reset_runtime() -> Iterator[None]:
    yield
    run._runtime = None  # noqa: SLF001


async def test_delete_thread_removes_checkpoints_and_is_idempotent() -> None:
    saver = InMemorySaver()
    run.use_runtime(saver)
    item_id = uuid.uuid4()
    config = {"configurable": {"thread_id": str(item_id), "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "1",
        "ts": "t",
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
    }
    await saver.aput(config, checkpoint, {}, {})  # type: ignore[arg-type]
    assert await saver.aget_tuple(config) is not None

    await run.delete_thread(item_id)
    await run.delete_thread(str(item_id))

    assert await saver.aget_tuple(config) is None
