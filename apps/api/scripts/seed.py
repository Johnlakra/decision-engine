"""Load demo items through ``ingest_one`` (no HTTP, no LLM) so a fresh install has a queue (FR-01).

Usage: ``python -m scripts.seed [--limit N]``. Idempotent: rows have stable ``source_ref`` values,
so a re-run creates nothing. ``--limit`` (default 50) protects the free-tier LLM budget, because
every new item enqueues a ``process`` job that the worker will run.
"""

import argparse
import asyncio
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import session_scope
from app.ingest.service import ingest_one
from app.models.tenant import Tenant
from app.schemas.ingest import IngestItemIn

DEFAULT_LIMIT = 50
DEFAULT_TENANT = "default"
SEED_RELATIVE_PATH = Path("seed") / "demo_items.jsonl"


@dataclass(frozen=True)
class SeedResult:
    created: int
    existing: int


def seed_file() -> Path:
    return get_settings().data_dir / SEED_RELATIVE_PATH


def load_rows(limit: int = DEFAULT_LIMIT, path: Path | None = None) -> list[IngestItemIn]:
    """Read and validate the first ``limit`` rows. Raises on a bad row (fail fast)."""
    if limit < 1:
        raise ValueError("--limit must be at least 1")
    source = path or seed_file()
    rows: list[IngestItemIn] = []
    with source.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if len(rows) >= limit:
                break
            if not line.strip():
                continue
            try:
                rows.append(IngestItemIn.model_validate(json.loads(line)))
            except ValueError as error:
                raise ValueError(f"{source}:{number}: invalid seed row: {error}") from error
    return rows


async def seed_items(
    session: AsyncSession, tenant_id: uuid.UUID, rows: Sequence[IngestItemIn]
) -> SeedResult:
    """Ingest each row; the caller commits."""
    created = 0
    for row in rows:
        _, is_new = await ingest_one(session, tenant_id, row)
        created += int(is_new)
    return SeedResult(created=created, existing=len(rows) - created)


async def run(limit: int) -> SeedResult:
    rows = load_rows(limit)
    async with session_scope() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.name == DEFAULT_TENANT).limit(1))
        if tenant is None:
            tenant = Tenant(name=DEFAULT_TENANT)
            session.add(tenant)
            await session.flush()
        return await seed_items(session, tenant.id, rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load synthetic demo items.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="max items (default 50)")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run(args.limit))
    except ValueError as error:
        print(f"seed: {error}", file=sys.stderr)  # noqa: T201 - CLI output
        return 2
    print(f"seeded: {result.created} new, {result.existing} already present")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
