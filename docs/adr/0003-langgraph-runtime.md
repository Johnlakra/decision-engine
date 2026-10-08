# 0003 — LangGraph runtime: dependencies, checkpointer, graph state

**Status:** accepted · 2026-10-08 · Requirements: FR-30, FR-31, FR-33, FR-34, NFR-03, NFR-04, NFR-06, NFR-12 ·
Plan: phase 1 steps A1, 1.4a, 1.4b, P, W (contract C7)

## Context
ADR 0001 chose LangGraph with the Postgres checkpointer for durable human-in-the-loop (`interrupt()`), but no
dependency, driver, table-ownership or state-shape decision was recorded. Phase 1 builds the graph. Facts that shape
the decision (all checked 2026-10-08):

- **Versions.** `langgraph` 1.2.14 (released 2026-10-06; requires `langchain-core>=1.4.7,<2`,
  `langgraph-checkpoint>=4.1,<5`, `langgraph-prebuilt`, `langgraph-sdk`, `xxhash`)
  ([PyPI langgraph](https://pypi.org/project/langgraph/1.2.14/)). `langgraph-checkpoint-postgres` 3.1.2
  (2026-08-07; requires `psycopg>=3.2`, `psycopg-pool>=3.2`, `orjson`)
  ([PyPI](https://pypi.org/project/langgraph-checkpoint-postgres/)). `psycopg` 3.3.6 (2026-09-18, LGPL-3.0,
  `binary` and `pool` extras) ([PyPI](https://pypi.org/project/psycopg/)). `psycopg-pool` 3.3.3 (2026-09-22).
- **The checkpointer is psycopg 3 only.** `AsyncPostgresSaver(conn)` takes a psycopg `AsyncConnection` or
  `AsyncConnectionPool`. Its own `from_conn_string` connects with
  `autocommit=True, prepare_threshold=0, row_factory=dict_row`
  ([source, `postgres/aio.py`](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/aio.py)).
  The README states `autocommit=True` is required for `.setup()` and `dict_row` is required for reads.
- **`setup()` owns its schema.** It creates `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`,
  `checkpoint_writes` and three `CREATE INDEX CONCURRENTLY IF NOT EXISTS … (thread_id)` indexes, tracked in its own
  `checkpoint_migrations` table. `CONCURRENTLY` cannot run inside a transaction (hence autocommit). `setup()` takes
  **no lock**, so two processes running it at once can race on `checkpoint_migrations`
  ([source, `postgres/base.py`](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/langgraph/checkpoint/postgres/base.py)).
- **Interrupts.** `from langgraph.types import interrupt, Command`. Resume with `ainvoke(Command(resume=value), config)`.
  An interrupted `ainvoke` returns a result with an `"__interrupt__"` key. When a node resumes, it re-runs **from
  its start**. `interrupt()` must not be wrapped in a bare `try/except` (it raises internally), call order must be
  stable, and its payload must be JSON-serialisable ([LangGraph docs, Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)).
- **Durability.** `invoke/stream(..., durability="exit"|"async"|"sync")`. The default `"async"` writes the checkpoint
  while the next step runs, with "a small risk" of a lost checkpoint if the process crashes. `"sync"` writes every
  checkpoint before the next step starts ([LangGraph docs, Durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution)).
- **Neon pooler.** Neon's pooled endpoint (`-pooler` host) is PgBouncer in `transaction` mode with
  `max_prepared_statements=1000` (protocol-level prepared statements work). It does **not** support `LISTEN/NOTIFY`,
  SQL `PREPARE`, `SET`, or **session-level advisory locks** ([Neon docs, Connection pooling](https://neon.com/docs/connect/connection-pooling)).
  A 0.25 CU compute allows 112 direct connections, 7 reserved
  ([Neon FAQ](https://neon.com/faqs/managed-postgres-services-serverless-connections)).
- **psycopg `prepare_threshold`.** `None` disables prepared statements; `0` prepares **every** query on first use (it
  does not disable them). Through PgBouncer, prepared statements need PgBouncer ≥ 1.22 with
  `max_prepared_statements > 0` and libpq ≥ 17, or `Connection.prepared_max = None`
  ([psycopg docs, Prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html)).
- **The app already needs session features.** The Phase 0 worker uses `LISTEN` (`workers/run.py`). Phase 1 C7 adds
  a session-level `pg_try_advisory_lock` per item. Both fail silently or incorrectly through a transaction pooler.
- **Checkpoint volume.** One graph run writes about one checkpoint per step (about 9 steps). On Neon Free's storage
  allowance (see `docs/DEPLOY.md`), keeping every thread forever does not fit NFR-04 at thousands of items per week.

## Options considered

### A. Driver for the checkpointer
| | (a) Add psycopg 3 next to asyncpg (checkpointer only) | (b) Move the whole app to psycopg 3 | (c) Custom checkpointer on asyncpg |
|---|---|---|---|
| Work | New `app/graph/checkpointer.py` only | Rewrite engine URL, the worker LISTEN code, test fixtures | Implement and maintain `BaseCheckpointSaver` (put, put_writes, list, get_tuple, delete_thread, migrations) |
| Free-tier cost | A second small pool (max 2 connections per process) | One pool | One pool |
| Ops burden | Two drivers to patch | Risky churn in working Phase 0 code | We own correctness of the most critical persistence path |
| Image size | `psycopg-binary` wheel (bundled libpq), a few MB | Same | None |

### B. Who owns the checkpoint tables
| | (a) `AsyncPostgresSaver.setup()` at start-up, excluded from Alembic | (b) Copy the DDL into an Alembic migration |
|---|---|---|
| Upgrades | A library upgrade adds its own migrations automatically | Every library upgrade needs a hand-written migration that tracks upstream DDL exactly |
| Rule fit | Exception to "schema change = Alembic migration" | Fits the rule |
| Risk | Two migration systems in one database | Drift between our copy and the library's `checkpoint_migrations` version table: the library would try to re-apply |

### C. Graph state contents
| | (a) Ids and derived data only (C7) | (b) ARCHITECTURE §3 shape, including `content` and `triage` |
|---|---|---|
| Privacy / retention | Checkpoints never hold bodies, so NFR-06 purges of `raw`/`content.body` stay complete | Every checkpoint copies the body: purging means rewriting checkpoint blobs |
| Storage | Small blobs | Body × steps per item |
| Cost | Nodes re-read the item (one indexed PK read per node) | No re-read |

### D. Durability mode
| | (a) `durability="sync"` | (b) default `"async"` |
|---|---|---|
| Crash safety | Every finished node is persisted before the next starts (P3 needs this: `extract` runs exactly once across a crash) | A crash can lose the last step, so a paid LLM call can be repeated |
| Cost | About one extra round trip per step (about 9 per item) | None |

## Decision
1. **Dependencies (exact pins, `apps/api/pyproject.toml`, resolved in `uv.lock`):** `langgraph==1.2.14`,
   `langgraph-checkpoint-postgres==3.1.2`, `psycopg[binary,pool]==3.3.6`. Transitive pins (`langgraph-checkpoint`,
   `langchain-core`, `psycopg-pool`, `langsmith`) come from `uv.lock`. If `uv lock` cannot resolve these exact versions
   together with `litellm==1.104.0`, the builder takes the newest resolving patch releases of the same minor series
   and reports them. A minor or major change needs a new ADR. **asyncpg stays** the SQLAlchemy driver (option A-a).
2. **Connection rules.**
   - `DATABASE_URL` must point at a **direct (non-pooler) endpoint**. On Neon that means the host without `-pooler`.
     The app needs `LISTEN`, session advisory locks and `CREATE INDEX CONCURRENTLY`. `core/config.py` logs a warning
     at start-up when the host contains `-pooler`, and `/health/deep` reports `"db_pooler": true`.
   - `app/graph/checkpointer.py: open_checkpointer(dsn) -> AsyncContextManager[AsyncPostgresSaver]` builds an
     `AsyncConnectionPool(conninfo, min_size=1, max_size=2, open=False, kwargs={"autocommit": True,
     "prepare_threshold": 0, "row_factory": dict_row})`, the same kwargs as the library's `from_conn_string`.
     The DSN is `database_url` with `+asyncpg` removed. Pool size 2 in the API process and 2 in the worker.
   - Correction to the plan: `prepare_threshold=0` **enables** prepared statements. It is correct on a direct
     endpoint. It is **not** the setting that makes a pooler safe. Pooled URLs are unsupported (see above).
3. **Table ownership (option B-a).** `python -m app.graph.setup` opens one direct psycopg connection
   (`autocommit=True`), takes `pg_advisory_lock(<constant key>)`, runs `AsyncPostgresSaver(conn).setup()`, then
   unlocks. It is idempotent. `docker-entrypoint.sh` runs it after `alembic upgrade head` in the `api` role **and**
   before the loop in the `worker` role, so start-up order does not matter and the lock removes the race.
   `alembic/env.py` gets an `include_object` that returns `False` for tables named `checkpoint_migrations`,
   `checkpoints`, `checkpoint_blobs` and `checkpoint_writes` (and their indexes), so autogenerate never drops them.
   This is the **only** exception to the CLAUDE.md rule "schema change = Alembic migration". Our own tables never
   use the `checkpoint` prefix. Test fixtures (`committed_db`) run `setup()` once per session and truncate the four
   tables after each test.
4. **Graph state (option C-a).** `GraphState` is the C7 TypedDict: `item_id`, `tenant_id`, `niche`, `niche_version`,
   `sensitivity`, `language`, `route`, `extracted`, `tool_results`, `decision`, `verdict`, `actions_done`. Values are
   JSON-native types only (`str`, `int`, `float`, `bool`, `None`, `list`, `dict`), no Pydantic objects, no `datetime`
   (ISO strings). This keeps serialisation inside the checkpointer's safe types. **Item `raw`, `content`, `hints` and
   bodies are never put in state.** Nodes read them from the DB. `extracted` and `tool_results` are derived data; a
   niche whose `extract` schema copies long text must cap each string at 500 chars before it enters state.
   This replaces the ARCHITECTURE §3 state, which listed `content` and `triage`.
5. **Durability (option D-a).** Every `ainvoke` in `graph/run.py` passes `durability="sync"`.
   Thread id = `str(item_id)`; `checkpoint_ns` is the default `""`.
6. **Interrupt rules (binding on node code, code-review focus).** Code before `interrupt()` re-runs on resume, so every
   pre-interrupt write is guarded by the current `items.status`. Side effects happen after `interrupt()` or in a later
   node. No `try/except Exception` encloses `interrupt()`. One `interrupt()` call per approval node execution.
7. **Thread clean-up.** When `run_item` / `resume_item` returns with the graph at `END` (item `done`, `informational` or
   `discarded`), it calls `checkpointer.adelete_thread(str(item_id))` in the same lock scope. Threads of items that are
   waiting (`awaiting_approval`, `snoozed`) or crashed mid-run are kept. Audit history lives in `decisions`,
   `feedback` and `actions_log`, not in checkpoints.
8. **One template.** `graph/builder.py` compiles one parameterised graph (load → route → extract → tools → decide →
   policy → approval → act → finish). A niche YAML with `steps:` fails with a clear error in Phase 1. Custom steps
   need a later ADR.
9. **One LLM door and privacy hold.** Graph nodes call `llm.gateway` only, never LangChain chat models. LangSmith
   tracing (a transitive dependency through `langchain-core`) must stay off: no `LANGSMITH_*` / `LANGCHAIN_*` tracing
   variables are set anywhere (compose, Render, `.env.example`). The `langgraph-sdk` dependency is unused.

## Consequences
- Two Postgres drivers and two pools per process (asyncpg with SQLAlchemy defaults, psycopg max 2). On Neon Free
  (105 usable direct connections) this is far below the limit. Idle connections keep the compute awake, but the worker's
  LISTEN connection already does that. `docs/DEPLOY.md` Profile B notes still apply.
- Profile B **cannot** use Neon's pooled URL for `DATABASE_URL`. If a future serverless API needs the pooler, add a
  separate `DATABASE_POOLED_URL` for the API engine only, through a new ADR.
- One deliberate exception to the "schema = migration" rule, isolated by name and guarded in `alembic/env.py`.
  `make migrate` alone does not create the checkpoint tables. Local scripts and tests must also run
  `python -m app.graph.setup` (the A1 fixtures do).
- NFR-06: checkpoints hold no bodies, and finished threads are deleted. The 180-day purge does not need to touch
  checkpoint blobs.
- Image size: `langchain-core` and `langsmith` (plus `requests`, `orjson`, `zstandard`, `jsonpatch`, `tenacity`) and
  `psycopg-binary` add to the image. The budget is **< 300 MB** uncompressed for the API image. backend-builder
  measures it in A1 (`docker image inspect -f '{{.Size}}'`) and reports the number. Over budget → report; do not
  drop features to fit.
- psycopg is LGPL-3.0. We use it unmodified as a dynamically loaded library in a service, which is fine.
- `durability="sync"` adds about 9 small writes per item. That is negligible against the LLM calls.

## Revisit when
- LangGraph or the checkpointer ships a new major version, or `setup()` gains its own locking.
- A deploy needs a transaction pooler (serverless API), or more than one worker replica runs against Neon Free.
- A niche needs custom `steps:`.

## Migration steps
1. backend-builder (A1): add the three pins and lock; add `include_object` to `alembic/env.py`; add the `-pooler`
   warning to `core/config.py`; add `committed_db` (runs setup once, truncates the four checkpoint tables).
2. langgraph-builder (1.4a): `app/graph/checkpointer.py` and `app/graph/setup.py` (advisory lock + `setup()`).
3. backend-builder (W): `docker-entrypoint.sh` runs `python -m app.graph.setup` in both the `api` and `worker` roles;
   `app/main.py` lifespan opens the checkpointer; the worker closes its pool on stop (P).
4. devops-deployer: document "direct endpoint only" for `DATABASE_URL` in `docs/DEPLOY.md` and `.env.example`, and make
   sure no `LANGSMITH_*` variable is set.
5. Rollback: remove the graph packages and drop the four `checkpoint*` tables by hand. No Alembic revision is involved.
