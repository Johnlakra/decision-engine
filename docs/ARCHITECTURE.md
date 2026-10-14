# Architecture

## 1. Components
```
                ┌──────────────────────────── apps/api (one image, two processes) ───────────────────────────┐
 connectors ──► │ FastAPI  /v1/items /v1/decide /v1/webhooks/*            worker (python -m app.workers.run) │
 (pollers run   │   │ validate, idempotency, raw store                       │ claims jobs (SKIP LOCKED)      │
  in worker)    │   └──► items(status=new) + jobs(kind=process) ───────────► │ normalise → triage → graph     │
                │                                                            │ actions, webhooks out, pollers │
                └─────────┬──────────────────────┬──────────────────────────┴───────┬────────────┬───────────┘
                          │                      │                                  │            │
                    Postgres+pgvector      Redis (optional)                   services/laya   LLM gateway
                    items, jobs, niches,   budgets, cool-downs,               laya-serve      (LiteLLM: Gemini,
                    decisions, feedback,   rate limits                        /v1/systemone   Groq, Cerebras,
                    LangGraph checkpoints                                     /batch          OpenRouter, Sarvam,
                                                                                              Ollama)
 apps/web (Next.js) ──► /v1 via server-side route handlers (API key never in the browser)
 apps/mobile (Expo) ──► /v1 with a device token (scoped key)       Telegram bot ──► /v1 (in worker process)
```

**Why these choices**
- *Postgres queue, not Redis/Celery*: Upstash free tier counts every command (500K/month) and Celery/arq
  poll constantly. A `jobs` table with `SKIP LOCKED` and adaptive polling (1 s when busy → 30 s idle,
  plus `NOTIFY` wake-up) costs nothing extra and is transactional with the item.
- *Laya as a separate service*: torch + weights ≈ 2–3 GB RAM; API image stays ~200 MB and fits Render free.
- *LangGraph*: native `interrupt()` + Postgres checkpointer gives durable human-in-the-loop for free.
- *LiteLLM*: one OpenAI-shaped interface over every provider with fallbacks; we add budgets + privacy on top.
- *Niches as YAML*: Laya's answer space is defined per request, so a new niche needs no training.

## 2. Item lifecycle (status machine)
```
new ─► normalised ─► triaged ─┬─► informational ─► done            (needs_decision = no)
                              ├─► discarded                        (news keep = skip, spam)
                              └─► deciding ─► awaiting_approval ─┬─► approved ─► acting ─► done
                                                                 ├─► rejected ─► done
                                                                 ├─► snoozed ─► awaiting_approval (at time)
                                                                 └─► auto_approved ─► acting ─► done
 any step ─► failed (after 5 retries; "retry" in UI)      triage unavailable ─► needs_human_triage
```

## 3. Graph (LangGraph)
```python
# ADR 0003: ids and derived data only. Item raw/content/hints/bodies are NEVER in state; nodes read them from the DB.
GraphState = TypedDict(item_id: str, tenant_id: str, niche: str, niche_version: int, sensitivity: str,
                       language: str, route: "decide"|"informational"|"discarded", extracted: dict,
                       tool_results: dict[str, dict], decision: dict | None, verdict: dict | None,
                       actions_done: list[dict])       # JSON-native values only (ISO strings, no datetime/Pydantic)

START → load → route ──┬─ needs_decision = no ─────────────────────────────► informational → END
                       ├─ niche == X & enabled & conf ≥ X.min_confidence ──► template(X)
                       └─ else ────────────────────────────────────────────► template(generic)
template(niche): extract (LLM, niche.extract schema) → tools (parallel, niche.tools) → decide (LLM,
                 niche.prompt + few-shot corrections → DecisionOut) → policy (autonomy, risk) →
                 approval (interrupt() unless auto-allowed; snooze loops back) → act (actions registry) → finish → END
```
- One parameterised template, compiled once by `graph/builder.py` and driven by the niche YAML. Niche `steps:`
  (custom step functions) are **rejected** until a later ADR (ADR 0003 §8).
- Checkpointer: `langgraph-checkpoint-postgres` `AsyncPostgresSaver` over a psycopg 3 pool (max 2 per process), next to
  asyncpg for SQLAlchemy. Its tables are created by `python -m app.graph.setup`, outside Alembic (ADR 0003).
  Thread id = `str(item_id)`. Every run uses `durability="sync"`. A thread is deleted when the graph reaches END.
- Code before `interrupt()` re-runs on resume, so pre-interrupt writes are guarded by `items.status`. The worker and
  the resume API both take `graph/locks.item_lock(item_id)` (session advisory lock, direct DB connection).
- `DecisionOut` (Pydantic, `app/schemas/decision.py`): `options[2..5]` each `{id A–E, label, actions[]}`,
  `recommended` (an option id), `rationale ≤ 600`, `evidence[]`, `deadline`, `confidence`. Stored as
  `items.decision` with `autonomy`, `needs_expert`, `warnings`, `model`, `niche_version`, `ready_at` added.

## 4. Folder layout (target)
```
apps/api/
  pyproject.toml  Dockerfile  alembic.ini  alembic/versions/
  app/
    main.py                  # FastAPI app factory, routers, lifespan
    core/config.py           # pydantic-settings: every env var, documented
    core/logging.py ids.py time.py errors.py
    db/session.py base.py     # async engine, session dependency
    models/                   # SQLAlchemy tables (docs/DATA_MODEL.md)
    schemas/                  # Pydantic I/O models; generated from/validated against /schemas/*.json
    api/v1/{items,uploads,decide,niches,sources,webhooks,subscriptions,feedback,stats,auth}.py
    ingest/service.py         # idempotent create, bulk, uploads job
    normalise/{mappers/,llm_normaliser.py,language.py,dedupe.py}
    triage/{laya_client.py,questions.py,fallback.py,service.py,calibration.py}
    niches/{loader.py,registry.py,wizard.py}
    graph/{state.py,checkpointer.py,setup.py,builder.py,run.py,locks.py,oneshot.py}
    graph/nodes/{load,route,extract,tools,decide,policy,approval,act,finish}.py
    tools/{registry.py,agmarknet.py,open_meteo.py,crop_calendar.py,web_search.py,stack_catalog.py,…}
    actions/{registry.py,generic.py,jobs.py,notify.py,gmail.py,telegram.py,…}
    integrations/{events.py,webhooks_out.py,ssrf.py}   # outbound events + signed webhook delivery (FR-42)
    connectors/{base.py,rss.py,gmail.py,instagram.py,telegram.py,webhook.py,csv.py,voice.py}
    llm/{gateway.py,providers.yaml,budgets.py,structured.py,privacy.py}
    feedback/{service.py,export.py,shadow_report.py}
    security/{api_keys.py,hmac.py,untrusted.py,crypto.py,rate_limit.py}
    workers/{run.py,queue.py,scheduler.py}
  tests/{unit,integration,fakes}/
apps/web/      app/(queue|history|niches|sources|insights|settings)  components/  lib/api.ts  messages/{en,hi,pa}.json
apps/mobile/   app/(tabs)/{queue,history,settings}.tsx  components/SwipeCard.tsx  lib/api.ts
packages/openapi.json                           # exported spec (make sdk)
packages/client-ts/  packages/client-py/        # thin SDKs generated from OpenAPI (ADR 0006: npm + Node 24)
services/laya/Dockerfile
niches/*.yaml  schemas/*.json  evals/*.jsonl  docs/  docs/adr/
docker-compose.yml  Makefile  .env.example  .github/workflows/ci.yml  render.yaml
```

## 5. Key interfaces (contracts builders must keep)
```python
# triage/laya_client.py
class LayaClient(Protocol):
    async def batch(self, states: list[str], questions: dict, *, model: str | None = None) -> list[dict | None]: ...
    # None per state = no opinion. Never raises for transport errors.

# llm/gateway.py
async def complete_json(purpose: str, schema: type[BaseModel], messages: list[dict], *,
                        sensitivity: Literal["public","private"], language: str = "en",
                        item_id: str | None = None) -> BaseModel: ...   # raises LLMUnavailable
async def complete_text(purpose: str, messages, *, sensitivity, language="en", item_id=None) -> str: ...

# tools/registry.py
@tool("agmarknet.prices", ttl=3600)
async def prices(commodity: str, state: str, district: str | None = None, days: int = 30) -> ToolResult: ...

# actions/registry.py
@action("archive", reversible=True)
async def archive(ctx: ActionContext, params: dict) -> ActionResult: ...

# connectors/base.py
class Connector(Protocol):
    slug: str
    async def poll(self, source: Source, since: datetime | None) -> AsyncIterator[IngestItem]: ...  # pull
    async def handle_webhook(self, source: Source, request: Request) -> list[IngestItem]: ...       # push
    def map(self, raw: dict) -> NormalisedContent | None: ...                                          # FR-11
```

## 6. Cross-cutting
- **Config**: every env var in `core/config.py` with default + comment, mirrored in `.env.example`.
- **Errors**: RFC 9457 problem+json for API errors.
- **IDs**: UUIDv7 (`uuid6` package or Python 3.14 `uuid.uuid7` if available).
- **Time**: all UTC; tenant timezone (default Asia/Kolkata) only for display, quiet hours, digests.
- **Feature flags**: env + `tenant_settings` JSONB (digest hour, and `laya_mode` / `laya_mode_by_niche`). Built today:
  the env `LAYA_MODE` and the worker reads of the stored `laya_mode` keys (`triage/modes.py`). **PLANNED (Phase 3 step
  3.5-B4, ADR 0008):** the API writes only `off`/`shadow`, and `on` is gated.
- **Niche overrides** (ADR 0009). **PLANNED (Phase 3 step 3.5-B1), not built:** `niches` rows replace the YAML niche
  of the same name. Each process keeps its own registry and calls `niches.overrides.sync_registry()` at the start of
  each unit of work (worker: once per non-empty claimed batch; API: decide, decision, niches routes). It reloads when
  `(count, sum(version), max(updated_at))` changes. Idle processes run no query. Today `NicheRegistry.reload(overrides=…)`
  accepts the argument but ignores it, and there is no `niches/overrides.py`.
- **Undo** (ADR 0007): a client-side 10 s hold before `POST /items/{id}/decision`, with no server state.
- **Rate limits** (FR-07): Redis fixed window when `REDIS_URL` is set, else an in-process window, so the limit
  is per process; more than one API process requires Redis (ADR 0002). The 5,000 items/day cap is **per tenant**,
  a count of today's (UTC) `items` rows, soft (ADR 0004).
- **Database URL**: `DATABASE_URL` must be a **direct** endpoint (on Neon: not the `-pooler` host). The worker's
  `LISTEN`, the per-item session advisory lock and the checkpointer's `CREATE INDEX CONCURRENTLY` do not work through
  a transaction pooler (ADR 0003).
- **Outbound webhooks** (FR-42): emitters call `integrations.events.emit()` inside their own transaction. It enqueues
  `jobs(kind=webhook, payload.op=fanout)`. The fan-out job writes one `webhook_deliveries` row and one `deliver`
  job per subscription. Delivery retries on its own schedule (1 m, 5 m, 30 m, 2 h after attempts 1–4, then `failed`
  as dead-letter), not the queue's generic backoff. See API.md "Outbound webhooks".
- **ADRs**: `docs/adr/NNNN-title.md` (context, decision, consequences) for any stack or contract change.
