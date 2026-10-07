# Decision Engine — CLAUDE.md
Standalone, API-first service that turns anything needing a decision (email, Instagram DMs, news,
webhooks, CSV, voice notes) into one JSON shape, triages it with **Laya** in milliseconds, sends only
what needs thought to a **LangGraph** niche agent backed by free-tier LLMs, and puts the result in a
human **approval queue**. Every human decision is saved as training data for Laya.

Read before any work: `docs/PLAN.md` (what phase we are in, what is next), then the doc for the area
you are touching. Requirements are numbered in `docs/REQUIREMENTS.md` (FR-/NFR-); cite them in
commits and tests (`# FR-21`).

## Stack (do not change without an ADR in docs/adr/, written by the architect agent)
| Layer | Choice |
|---|---|
| API + workers | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + Alembic, uv for deps |
| Orchestration | LangGraph (Postgres checkpointer), `interrupt()` for human approval |
| Triage model | Laya via `laya-serve` HTTP (`services/laya/`), never imported into the API image |
| LLMs | `apps/api/app/llm/gateway.py` only: LiteLLM router, fallback chain, daily budgets, privacy routing |
| DB | Postgres 16 + pgvector (Neon in the cloud, container locally) |
| Cache/budgets | Redis (Upstash or container) — optional; Postgres fallback; keep command counts low |
| Queue | Postgres `jobs` table with `FOR UPDATE SKIP LOCKED`; adaptive polling (no Redis polling) |
| Web | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query, `apps/web` |
| Mobile | Expo (React Native) + expo-router + Reanimated + gesture-handler, `apps/mobile` |
| Tests | pytest (+ pytest-asyncio, respx), Vitest + Playwright (web), Jest (mobile) |
| Deploy | Docker Compose (all-in-one VM) or Render + Neon + Upstash; Laya on a ≥4 GB box |

## Layout
```
apps/api/app/{api,core,db,models,schemas,ingest,normalise,triage,graph,niches,agents,tools,actions,
              connectors,llm,feedback,workers,security}   apps/api/tests/   apps/api/alembic/
apps/web/   apps/mobile/   packages/client-ts/   packages/client-py/
services/laya/   niches/*.yaml   schemas/*.json   evals/<niche>.jsonl   docs/   docs/adr/
```

## The pipeline (one item)
`ingest` (validate, idempotency on source+source_ref, store raw) → `normalise` (LLM structured output
→ `DecisionItem.content`; cheap path for already-structured JSON) → `triage` (one Laya batch call:
needs_decision, niche, urgency, risk + the niche's own questions) → `route` (confidence gate) →
niche subgraph (tools + LLM → options, recommendation, rationale) → `approval` (`interrupt()`, per
niche autonomy) → `act` (actions registry, idempotent) → `feedback` (every human answer stored).

## Rules
- **Niches are config, not code.** A niche = `niches/<name>.yaml` validated by `schemas/niche.schema.json`.
  Code adds *tools* and *actions* to registries; YAML picks which a niche uses. Never hardcode a niche name
  in pipeline code except the `generic` fallback.
- **One LLM door.** All model calls go through `llm.gateway` (budgets, fallback, logging, privacy). No
  provider SDK imports anywhere else.
- **Laya can never lose an item.** Laya down/slow/garbled = "no opinion" → LLM fallback classifier or
  the human queue. Ship Laya features in `shadow` mode first; only `docs/LAYA.md` calibration unlocks `on`.
- **Privacy.** Items with `sensitivity: private` (email bodies, DMs by default) go only to providers marked
  `private_ok` (local Ollama or a paid tier whose terms allow it). Never log full bodies; log ids.
- **Untrusted text is data.** Every remote string reaching a prompt passes `security.as_data()` (strip
  control chars, cap length, fenced). Prompts state that content is data, never instructions. Model
  output never becomes a URL, shell command, SQL or action without validation.
- **Irreversible actions need approval.** Send, delete, reply, pay, post: always `interrupt()` unless the
  niche autonomy is `auto` AND the action is in that niche's `auto_actions` allow-list.
- **Agriculture safety.** Pesticide/fertiliser/dose advice is always `ask` autonomy with an expert-review
  flag; output carries data dates and sources; never "guaranteed".
- **Platform rules.** Instagram: official API, professional accounts, 24 h window, no scraping. Gmail:
  restricted scopes, Testing mode until CASA. No auto-signup, no trading, no wallet keys.
- **Free tiers first.** Every external call has a daily budget (FR-60s). Cache what can be cached.
- **Schema changes = Alembic migration** in the same commit. Never edit an applied migration.
- **IDs**: UUIDv7 strings. Times: UTC `timestamptz`, ISO 8601 in JSON.
- **Tests before done.** `make test` green; new behaviour has tests; external HTTP mocked with respx;
  LLM and Laya faked through their clients' test doubles (`tests/fakes/`).
- **Secrets** only from env (`app/core/config.py`, pydantic-settings). Never read or print `.env`.
- American English in UI copy and docs. UI strings go through i18n (en, hi, pa).
- Commits: Conventional Commits (`feat(triage): ...`), reference FR ids, small and green.

## Agent team (`.claude/agents/`, see docs/AGENTS.md)
Subagents cannot call each other — the main session orchestrates, usually via `/build-phase N`.
planner → architect (when design changes) → builders in parallel where files do not overlap →
test-writer → code-reviewer → security-auditor (before deploy) → docs-keeper ticks `docs/PLAN.md`.

## Commands
`make dev` (compose up), `make test`, `make lint` (ruff + mypy + eslint), `make migrate`,
`make laya-up` (Laya service), `make seed` (demo items), `make eval NICHE=x` (Laya/LLM eval on evals/x.jsonl).
