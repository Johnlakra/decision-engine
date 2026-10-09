"""Worker process: claim, run, retry. Entry point: ``python -m app.workers.run``."""

import asyncio
import contextlib
import signal
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger, log_context
from app.core.time import TENANT_TZ
from app.db.session import async_session_factory
from app.models.enums import ItemStatus, JobKind, JobStatus
from app.models.item import Item
from app.models.job import Job
from app.models.status import can_transition, transition
from app.workers import queue
from app.workers.handlers import HANDLERS, Handler, UnsupportedJob
from app.workers.pipeline import prepare_batch

log = get_logger("app.workers")

MIN_POLL_S = 1.0
RECLAIM_EVERY_S = 60.0

Prepare = Callable[[async_sessionmaker[AsyncSession], Sequence[Job]], Awaitable[None]]


def is_active_hour(now_local: datetime, spec: tuple[int, int]) -> bool:
    start, end = spec
    return start <= now_local.hour < end


def next_poll_delay(idle_streak: int, max_s: int) -> float:
    """1 s after the first empty poll, doubling up to ``max_s``."""
    exponent = min(max(idle_streak - 1, 0), 30)
    return float(min(MIN_POLL_S * 2**exponent, max(max_s, MIN_POLL_S)))


def asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


class Worker:
    def __init__(
        self,
        worker_id: str,
        settings: Settings,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        handlers: Mapping[JobKind, Handler] | None = None,
        prepare: Prepare | None = None,
        manage_graph: bool = True,
    ) -> None:
        self.worker_id = worker_id
        self.settings = settings
        self._factory = session_factory or async_session_factory()
        self._handlers = handlers if handlers is not None else HANDLERS
        self._prepare = prepare
        self._manage_graph = manage_graph
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._last_reclaim = 0.0

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    async def run_once(self) -> int:
        """Claim one batch and process it. Returns the number of jobs claimed."""
        async with self._factory() as session:
            jobs = await queue.claim(
                session, worker_id=self.worker_id, limit=self.settings.worker_batch_size
            )
            await session.commit()
        if jobs and (prepare := self._prepare) is not None:
            await self._run_prepare(prepare, jobs)
        for index, job in enumerate(jobs):
            if self._stop.is_set():
                async with self._factory() as session:
                    await queue.release(session, jobs[index:])
                    await session.commit()
                break
            await self._process(job)
        return len(jobs)

    async def _run_prepare(self, prepare: Prepare, jobs: list[Job]) -> None:
        try:
            await prepare(self._factory, jobs)
        except Exception:
            log.exception("prepare hook failed; handlers continue")

    async def _process(self, job: Job) -> None:
        with log_context(job_id=job.id, tenant_id=job.tenant_id, **self._item_ctx(job)):
            handler = self._handlers.get(JobKind(job.kind))
            try:
                if handler is None:
                    raise UnsupportedJob(job.kind)
                async with self._factory() as session:
                    await handler(session, job)
                    await queue.complete(session, job.id)
                    await session.commit()
                log.info("job done", extra={"kind": job.kind})
            except Exception as exc:
                error = queue.describe_exception(exc)
                log.warning(
                    "job failed", extra={"kind": job.kind, "error": error, "attempts": job.attempts}
                )
                await self._record_failure(job, error)

    @staticmethod
    def _item_ctx(job: Job) -> dict[str, uuid.UUID]:
        return {"item_id": job.item_id} if job.item_id else {}

    async def _record_failure(self, job: Job, error: str) -> None:
        async with self._factory() as session:
            status = await queue.fail(session, job, error)
            if status is JobStatus.FAILED and job.item_id:
                item = await session.get(Item, job.item_id, with_for_update=True)
                if item and can_transition(item.status, ItemStatus.FAILED):
                    transition(item, ItemStatus.FAILED)
            await session.commit()

    async def _maybe_reclaim(self) -> None:
        if time.monotonic() - self._last_reclaim < RECLAIM_EVERY_S:
            return
        self._last_reclaim = time.monotonic()
        async with self._factory() as session:
            count = await queue.reclaim_stale(session)
            await session.commit()
        if count:
            log.warning("reclaimed stale jobs", extra={"count": count})

    async def _listen(self) -> asyncpg.Connection | None:
        try:
            conn = await asyncpg.connect(asyncpg_dsn(self.settings.database_url))
            await conn.add_listener(queue.NOTIFY_CHANNEL, lambda *_: self._wake.set())
            return conn
        except Exception as exc:
            log.warning("LISTEN unavailable, polling only", extra={"error": type(exc).__name__})
            return None

    async def _sleep(self, seconds: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        self._wake.clear()

    async def _open_graph(self) -> None:
        if not self._manage_graph:
            return
        from app.graph.run import open_runtime

        try:
            await open_runtime()
        except Exception:
            log.exception("graph runtime failed to open; will retry on first use")

    async def _close_graph(self) -> None:
        if not self._manage_graph:
            return
        from app.graph.run import close_runtime

        try:
            await close_runtime()
        except Exception:
            log.exception("graph runtime close failed")

    async def run_forever(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.stop)
        listener = await self._listen()
        await self._open_graph()
        max_s = self.settings.worker_idle_poll_seconds
        idle = 0
        log.info("worker started", extra={"worker_id": self.worker_id})
        try:
            while not self._stop.is_set():
                if not is_active_hour(datetime.now(TENANT_TZ), self.settings.worker_active_hours):
                    await self._sleep(max_s)
                    continue
                try:
                    await self._maybe_reclaim()
                    claimed = await self.run_once()
                except Exception:
                    log.exception("worker iteration failed")
                    claimed = 0
                idle = 0 if claimed else idle + 1
                if not claimed:
                    await self._sleep(next_poll_delay(idle, max_s))
        finally:
            if listener is not None:
                await listener.close()
            await self._close_graph()
            log.info("worker stopped", extra={"worker_id": self.worker_id})


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    worker = Worker(f"worker-{uuid.uuid4().hex[:8]}", settings, prepare=prepare_batch)
    asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
