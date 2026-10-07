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
State = TypedDict(item_id, tenant_id, content, triage, niche, tool_results, decision, approval, actions_done)

START → load_item → route ──┬─ niche == X & conf ≥ niche.min_confidence ─► X subgraph
                            └─ else ─────────────────────────────────────► generic subgraph
niche subgraph:  extract (LLM, niche.extract schema) → tools (parallel, niche.tools) → decide (LLM,
                 niche.prompt + few-shot corrections → DecisionOut) → policy (autonomy, risk) →
                 approval (interrupt() unless auto-allowed) → act (actions registry) → END
```
- Subgraphs are built **from YAML** by `graph/builder.py`: one generic subgraph template, parameterised.
  A niche needing custom steps declares `steps:` referencing registered step functions.
- Checkpointer: `langgraph-checkpoint-postgres` (`AsyncPostgresSaver`), thread id = item id.
- `DecisionOut` (Pydantic): `options[2..5]`, `recommended`, `rationale`, `deadline`, `actions[]`, `confidence`.

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
    graph/{state.py,builder.py,nodes.py,policy.py,run.py}
    tools/{registry.py,agmarknet.py,open_meteo.py,crop_calendar.py,web_search.py,stack_catalog.py,…}
    actions/{registry.py,archive.py,notify.py,webhook.py,gmail.py,telegram.py,…}
    connectors/{base.py,rss.py,gmail.py,instagram.py,telegram.py,webhook.py,csv.py,voice.py}
    llm/{gateway.py,providers.yaml,budgets.py,structured.py,privacy.py}
    feedback/{service.py,export.py,shadow_report.py}
    security/{api_keys.py,hmac.py,untrusted.py,crypto.py,rate_limit.py}
    workers/{run.py,queue.py,scheduler.py}
  tests/{unit,integration,fakes}/
apps/web/      app/(queue|history|niches|sources|insights|settings)  components/  lib/api.ts  messages/{en,hi,pa}.json
apps/mobile/   app/(tabs)/{queue,history,settings}.tsx  components/SwipeCard.tsx  lib/api.ts
packages/client-ts/  packages/client-py/        # thin SDKs generated from OpenAPI
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
- **Feature flags**: env + `tenant_settings` JSONB (laya_mode, autonomy overrides, digest hour).
- **Rate limits** (FR-07): Redis fixed window when `REDIS_URL` is set, else an in-process window, so the limit
  is per process; more than one API process requires Redis (ADR 0002).
- **ADRs**: `docs/adr/NNNN-title.md` (context, decision, consequences) for any stack or contract change.
