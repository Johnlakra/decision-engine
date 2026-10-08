# Phase 1: Core pipeline + first niches (no connectors), implementation plan

Source: docs/PLAN.md §Phase 1 (steps 1.1–1.11). Specs used: CLAUDE.md, docs/{REQUIREMENTS,ARCHITECTURE,DATA_MODEL,API,LAYA,LLM_GATEWAY,NICHES,AGENTS}.md,
schemas/*.json, niches/*.yaml, ADR 0001/0002, and the Phase 0 code in `apps/api` (commits 6a90b04..1c86730), which is treated as existing.

## Goal
`POST /v1/items` (or `POST /v1/decide`) produces a real decision that waits for approval through the API. Approval resumes the
LangGraph thread, runs the allowed actions and emits signed webhooks. Every human verdict becomes feedback. **Laya stays in `shadow`
(env default) or `off`. Nothing in this phase sets `on` by default.** `on` is implemented and tested only through an explicit tenant setting in tests.

## What exists (Phase 0) that this plan builds on, with signatures it must keep
- `workers/queue.py`: `enqueue(session, *, tenant_id, kind: JobKind, item_id=None, payload=None, run_at=None, max_attempts=5) -> UUID`, `claim`, `complete`,
  `fail`, `release`, `reclaim_stale(session, lease=...)`, `queue_stats`. `workers/handlers.py`: `HANDLERS: Mapping[JobKind, Handler]`, `Handler = (AsyncSession, Job) -> Awaitable[None]`.
  `handle_process` is a **stub** (new → normalised). `workers/run.py`: `Worker(worker_id, settings, *, session_factory=None, handlers=None)`, `run_once()`. The handler and `queue.complete` share one transaction.
  `Worker._process` catches `Exception` only.
- `models/status.py`: `transition(item, to)`, `can_transition`. This is the only writer of `items.status`. The flow already allows every Phase 1 path (triaged→deciding→awaiting_approval→approved/rejected/snoozed→…).
- `models/enums.py`: `ItemStatus, JobKind(process, action, webhook, poll, upload, digest), Verdict, DecidedBy, FeedbackKind, LabelSource, DeliveryStatus(pending, delivered, failed), ActionStatus`.
- Tables: `items` (no `hints`/`callback_url` column), `decisions`, `feedback`, `actions_log` (UNIQUE tenant_id+idem_key), `webhook_subscriptions` (secret_enc), `webhook_deliveries`, `tenant_settings.settings jsonb`.
- `triage/laya_client.py`: `LayaClient` Protocol, `HttpLayaClient.from_settings`. Each result is `{"answers": {qid: {type, choice|score+level|noul, probabilities, confidence, answer_confidence}}, "model", "laya_version", "latency_ms"}`, and a result is `None` on failure.
  `tests/fakes/fake_laya.py`: `FakeLayaClient(responses=None, *, fail=False)`.
- `llm/gateway.py`: `complete_json(purpose, schema, messages, *, sensitivity, language="en", item_id=None, max_tokens=None)`, `complete_text(...)`. Both raise `LLMUnavailable` / `NoPrivateProvider`.
  The purposes with chains are `normalise, classify, decide, summarise, draft`. `llm/fence.py`: `fence(content, source)`. `tests/fakes/fake_llm.py`: the `fake_llm` fixture, `FakeLLM.script(purpose, ...)` and `Failure`.
- `niches/registry.py`: `get_registry()`, `NicheRegistry.get/enabled/all/reload`. `niches/models.py`: `NicheConfig` (triage.min_confidence, triage.questions, discard_if, extract, tools, prompt, options_hint, actions, autonomy, auto_actions, few_shot, llm.purpose_decide/max_tokens).
- `security/`: `as_data`, `hmac.sign/verify` (header `t=<unix>,v1=<hex>`), `crypto.encrypt/decrypt`. `api/deps.py`: `require_scope(scope)`, `Principal(tenant_id, api_key_id, scopes)`.
- `tests/conftest.py`: `db_session` (rolled-back transaction), `tenant`, `settings_env`. Graph/worker integration tests need **committed** data, so a new fixture is required (A1).

## Acceptance checks (executable)
Run from the repo root. `$KEY` comes from `make api-key SCOPES=admin`. The fake-based tests (P1–P4) are the CI gate. The live checks (L1–L3) are run by the main session or the owner.

| # | Check | Command | Pass when |
|---|---|---|---|
| P1 | School-ERP decision (fakes) | `cd apps/api && uv run pytest -q -m integration tests/integration/acceptance/test_p1_school_erp.py` | item ends `awaiting_approval`, `niche=tech_stack`, `decision.options` 2–5, `recommended` ∈ option ids, rationale ≤ 3 sentences, `decision.autonomy="suggest"`, `triage.mode="shadow"`, and the decide prompt contained `stack_catalog.shortlist` output (real tool over `data/stacks.yaml`) |
| P2 | Approve → signed webhook | `… tests/integration/acceptance/test_p2_approve_webhook.py` | `POST /v1/subscriptions` (receiver = stdlib `http.server` thread on 127.0.0.1, `WEBHOOK_ALLOW_PRIVATE_URLS=true`), `POST /v1/items/{id}/decision {"verdict":"approve"}` → `200 {"status":"done"}`. Worker run → receiver got `decision.made` with `X-DE-Signature` passing `security.hmac.verify(secret, body, header)`, and `body.data.id == item id`. Receiver 500 on the 1st try → `attempts=1`, `next_attempt_at ≈ now+60 s`, and delivered after the due time is forced. Exactly one `decisions` row and one `feedback` row (kind `decision`) |
| P3 | Crash mid-graph resumes | `… tests/integration/acceptance/test_p3_crash_resume.py` | FakeLLM `decide` raises `SimulatedCrash(BaseException)` once (escapes `Worker._process`, so the job stays `running`) → `reclaim_stale(lease=timedelta(0))` → second worker run. Final `awaiting_approval`. **`extract` was called exactly once in total** (resumed from checkpoint, not restarted). One `decision.ready` delivery |
| P4 | Laya down, nothing lost | `… tests/integration/acceptance/test_p4_laya_down.py` | (a) shadow + `FakeLayaClient(fail=True)` → `triage.decided_by="llm_fallback"` and `triage.shadow.error="laya_unavailable"`. (b) tenant `laya_mode=on` + fail → `llm_fallback`. (c) Laya fail + FakeLLM classify `Failure.TIMEOUT` → `needs_human_triage`, job `done`. (d) `HttpLayaClient` aimed at a closed port, 10 items → `count(items)=10`, every one in {`awaiting_approval`, `needs_human_triage`}, none `new`/`failed` |
| P5 | Quality gate | `make lint && make test` | green. The acceptance tests ran (not skipped) when Postgres is reachable. CI always runs them |
| P6 | Migration reversibility | `cd apps/api && uv run alembic upgrade head && uv run alembic downgrade 0001 && uv run alembic upgrade head` | no errors |
| P7 | Laya never defaults to `on` | `uv run pytest -q tests/unit/triage/test_modes.py` and `! grep -RnE "LAYA_MODE=on|laya_mode: *on" .env.example docker-compose.yml apps/api/scripts niches` | green; grep finds nothing |
| P8 | SDKs are current | `make sdk && git diff --exit-code packages/` | no diff |
| P9 | Seed | `make seed` then `docker compose exec db psql -U de -d de -tc "select count(*) from items where source='seed'"` | `50` (rerun → still 50, idempotent) |
| P10 | Feedback export | after P2 (or L2): `curl -fsS -H "Authorization: Bearer $KEY" "localhost:8000/v1/feedback/export?niche=tech_stack&format=laya_train"` | JSONL; every line has `state`, `questions`, `gold` |
| L1 | Live school-ERP | `make dev`, then `make accept-phase1` (runs `scripts/accept_phase1.py`: POST the brief, poll ≤ 120 s, print decision) | exit 0, `awaiting_approval`, `niche=tech_stack`, ≥ 2 options. Needs a Gemini or Groq key |
| L2 | Live webhook | `uv run python -m scripts.webhook_receiver --port 9099 --secret s3cr3t`, then `curl -X POST /v1/subscriptions {"url":"http://host.docker.internal:9099/hook","events":["decision.made"],"secret":"s3cr3t"}`, then approve the L1 item | receiver prints `signature OK decision.made <id>`. Needs `TOKEN_ENC_KEY` and `WEBHOOK_ALLOW_PRIVATE_URLS=true` in `.env` (dev only) |
| L3 | Live Laya down | `make laya-up`, then `docker compose stop laya`, then `make accept-phase1` | still exit 0. `triage.shadow.error="laya_unavailable"` |

Fallbacks: without an LLM key, L1–L3 are recorded as *pending owner key* and P1–P4 are the gate. Without Docker, run P1–P6 against local Postgres (as in Phase 0).

---

## Shared contracts (all steps code against these; changing one needs the architect)
Paths are relative to `apps/api/` unless they start with `/`.

**C1 Schemas (`app/schemas/`, written in A1, read by everyone)**
- `content.py`: `NormalisedContent(title: str ≤ 500, body: str = "", summary: str | None, sender: str | None, url: str | None, language: str | None, entities: dict = {}, attachments: list[dict] = [], flags: list[str] = [])`. `flags` may contain `normalise_failed`.
- `triage.py`: `Answer(type: Literal["choice","score","noul"], choice: str | None, score: float | None, level: int | None, noul: float | None, probabilities: dict[str, float], confidence: float | None, source: Literal["laya","llm_fallback","hint","human"])`.
  `TriageRecord(mode: Literal["off","shadow","on"], model: str | None, laya_version: str | None, fallback: bool, decided_by: Literal["laya","llm_fallback","human"], answers: dict[str, Answer], questions: dict[str, dict], shadow: ShadowRecord | None, latency_ms: int, error: str | None)`.
  `ShadowRecord(answers: dict[str, Answer] | None, model: str | None, latency_ms: int | None, error: str | None)`. This is stored as `items.triage` (DATA_MODEL shape plus the additive `questions`, `shadow`, `source`, `error` fields).
- `decision.py`: `ActionSpec(type: str, params: dict = {})`. `Option(id: str matching ^[A-E]$, label: str ≤ 300, actions: list[ActionSpec] = [])`. `Evidence(kind: Literal["field","tool"], ref: str, as_of: str | None)`.
  **`DecisionOut`** (the LLM schema): `options: list[Option]` (2–5, unique ids), `recommended` (must be an option id), `rationale ≤ 600`, `evidence = []`, `deadline: datetime | None`, `confidence: float` 0–1.
  `StoredDecision(DecisionOut)`: `autonomy`, `needs_expert = False`, `warnings: list[str] = []`, `model: str | None`, `niche_version: int`, `ready_at: datetime | None`. This is `items.decision`.
  `DecisionIn` (resume body, API.md): `verdict: Verdict`, `option: str | None`, `edits: dict | None`, `snooze_until: datetime | None` (required and in the future for `snooze`), `note: str | None ≤ 1000`.
- `ingest.py`: `Hints`, `IngestItemIn` (mirrors `/schemas/ingest_item.schema.json`, `extra="forbid"`), `IngestResult(id, status)`, `BulkIn(items ≤ 500)`, `BulkRow(index, id?, status?, error?)`.
- `items.py`: `DecisionItemOut` (mirrors `decision_item.schema.json`, **never includes `raw` or `hints`**) and `item_to_public(item: Item, last_decision: Decision | None) -> DecisionItemOut`. This is used by GET routes and webhook payloads.

**C2 Events (`app/integrations/events.py`, A2)**: `EventName = Literal["item.triaged","decision.ready","decision.made","action.done"]`.
`async emit(session, *, tenant_id: UUID, event: EventName, item_id: UUID, extra: dict | None = None) -> None`. It runs in the caller's transaction.
If no enabled subscription lists `event`, it returns without writing. Otherwise it enqueues `JobKind.WEBHOOK` with payload `{"op":"fanout","event","event_id":"evt_<uuid7>","extra"}`.
Emitters: triage → `item.triaged`; approval node → `decision.ready` and `decision.made`; act node → `action.done` per executed action.

**C3 Tools (`app/tools/registry.py`, A3)**: `ToolResult(name: str, data: dict, as_of: str | None, source: str | None)`.
`@tool(name: str, *, ttl_s: int, args: type[BaseModel], private_ok: bool = False)` decorates `async fn(args) -> ToolResult`.
`registered() -> frozenset[str]`. `async run_tool(name, extracted: dict, *, sensitivity) -> ToolResult | None`: it validates `args.model_validate(extracted)` (extra ignored), skips non-`private_ok` tools for private items, uses an in-process TTL cache keyed by sha256(name+canonical args), and returns `None` (logged) on any error.

**C4 Actions (`app/actions/registry.py`, 1.5)**: `ActionContext(session, tenant_id, item_id, option_id: str | None)`, `ActionResult(ok: bool, data: dict, error: str | None = None)`.
`@action(name, *, reversible=False, params: type[BaseModel])`. Params models use `extra="forbid"` and have no URL/email fields (NFR-07). `registered() -> frozenset[str]`.
`idem_key(item_id, name, params) -> str` = sha256(`f"{item_id}|{name}|{canonical_json(params)}"`).
`async run_action(ctx, name, params) -> ActionResult`: INSERT `actions_log … ON CONFLICT (tenant_id, idem_key) DO NOTHING`. A repeat returns the stored result. An unknown action returns `ok=False, error="unknown_action"`. A failure is recorded as `failed` and never raises. **Actions never write `items.status`.**
`async handle_action_job(session, job)` handles payload `op="reminder_due"`.

**C5 Triage (`app/triage/`, 1.3)**: `state_text(content: dict) -> str` (title + sender + first 600 body chars through `as_data`; the one builder for live, eval and export).
`core_questions(enabled: list[NicheConfig]) -> dict`, `niche_questions(niche) -> dict`, `resolve_mode(tenant_settings: dict, niche: str | None, default: str) -> Literal["off","shadow","on"]`.
`get_laya_client() -> LayaClient | None` (cached from settings; tests monkeypatch it).
`async triage_items(session, items: Sequence[Item]) -> list[TriageOutcome(item_id, status)]` does **one** Laya batch for all items, sets `items.triage/niche/urgency/risk/laya_mode`, transitions `normalised → triaged | needs_human_triage | discarded`, and emits `item.triaged`. It never raises for Laya or LLM failure.

**C6 Normalise (`app/normalise/`, 1.2)**: `async normalise_item(session, item) -> None` sets `items.content` (NormalisedContent dump) and `items.language`, then transitions `new → normalised`. It never raises for LLM failure (title fallback + `normalise_failed` flag).
`detect_language(text) -> str` (Gurmukhi→`pa`, Devanagari→`hi`, Latin with ≥ 2 Hindi function words→`hinglish`, else `en`). Priority: hint > LLM normaliser > heuristic.

**C7 Graph (`app/graph/`, 1.4)**: `GraphState` TypedDict = `item_id, tenant_id: str; niche: str; niche_version: int; sensitivity; language; route: Literal["decide","informational","discarded"]; extracted: dict; tool_results: dict[str, dict]; decision: dict | None; verdict: dict | None; actions_done: list[dict]`.
**Item content and bodies are never put in graph state.** Nodes read them from the DB, so checkpoints hold ids and derived data only (NFR-06 retention).
Thread id = `str(item_id)`.
`graph/run.py`: `async run_item(item_id) -> GraphOutcome(status, interrupted)` starts the thread, or continues it with `ainvoke(None)` when a checkpoint exists without an interrupt, or does nothing when it is already interrupted.
`async resume_item(item_id, tenant_id, body: DecisionIn) -> GraphOutcome` raises `NotAwaitingApproval` / `ItemBusy` (both map to 409).
`async unsnooze_item(item_id) -> None`. `graph/locks.py: item_lock(item_id)` is a session-level `pg_try_advisory_lock` on a dedicated connection. The worker and the resume API both take it, and API sessions never hold an item row lock while the graph runs.
Each node opens its own short `session_scope()` and is idempotent on re-execution. Code before `interrupt()` re-runs on resume, so its transitions are guarded by the current status.

**C8 Feedback (`app/feedback/service.py`, 1.9)**: `async record_decision_feedback(session, *, item: Item, body: DecisionIn, decided_by: DecidedBy, latency_ms: int | None) -> Feedback`.
`gold = {"answers": {qid: {key: 1.0}}, "decision": {"verdict","option","edited": bool}}`, `state_text` capped at 700 chars, `questions = item.triage.questions`.
`async iter_export(session, *, tenant_id, niche, fmt: Literal["laya_train","laya_eval"], since: datetime | None) -> AsyncIterator[str]`.

**C9 Worker hook (1.P)**: the `Worker` gains optional `prepare: Callable[[async_sessionmaker, list[Job]], Awaitable[None]]`, called after claim. It never raises. It normalises every claimed `new` item and triages every `normalised` one in **one** `triage_items` call (FR-20).
The per-job `process` handler stays correct alone: it is idempotent by `items.status` (normalise if `new`, triage if `normalised`, `run_item` if `triaged`/`deciding`). It commits its session before calling `run_item`.

---

## Ordered steps
Conventions: tests first (RED → GREEN), FR ids in test docstrings, `make lint && make test` green. Each step stays inside its files and reports any other needed change instead of making it.

### A1 Contracts, deps, migration, config, fixtures (backend-builder, M+M, two commits) | FR-01, FR-06, FR-07, FR-33, NFR-12
*Blocked by ADR 0003 + 0004 (see the ADR list).*
Files: `pyproject.toml`, `uv.lock` (add `langgraph`, `langgraph-checkpoint-postgres`, `psycopg[binary]`, all exact pins. mypy strict modules += `app.graph.*, app.actions.*, app.integrations.*, app.normalise.*, app.tools.*, app.feedback.*, app.ingest.*`),
`app/core/config.py` + `/.env.example` (`items_per_day=5000`, `data_dir=<repo>/data`, `webhook_allow_private_urls=False` (prod validator rejects true), `webhook_timeout_seconds=10`, `decide_timeout_seconds=30`),
`app/models/item.py` (`hints jsonb null`, `callback_url text null`), `alembic/versions/0002_item_hints.py` (those two columns + `ix_items_tenant_created(tenant_id, created_at)`; reversible), `alembic/env.py` (`include_object` ignores LangGraph `checkpoint*` tables),
`app/schemas/{content,triage,decision,ingest,items}.py` (C1), `tests/conftest.py` (add `committed_db` (truncates all app tables + checkpoint tables after the test), `api_client` (httpx ASGI), `admin_key`, `tenant_committed`),
`tests/unit/schemas/test_*.py`, `tests/integration/test_migration_0002.py`.
Tests first: DecisionOut rejects 1 or 6 options, duplicate ids, and a `recommended` that is not an option id. DecisionIn snooze requires a future `snooze_until`. `item_to_public` never contains `raw`/`hints`. IngestItemIn rejects unknown keys and a `source` pattern violation. Migration up/down/up.

### A2 Event emitter (integration-builder, S) | FR-42
Files: `app/integrations/__init__.py`, `app/integrations/events.py` (C2), `tests/unit/integrations/test_events.py`, `tests/integration/test_events_emit.py`.
Tests first: no subscription → no job row. A matching subscription → one `webhook` job with a `fanout` payload in the caller's transaction (rollback → no job). A disabled subscription is ignored.

### A3 Tool registry (langgraph-builder, S) | FR-32
Files: `app/tools/__init__.py`, `app/tools/registry.py` (C3), `tests/unit/tools/test_registry.py`.
Tests first: duplicate name rejected. Args validated (extra ignored, wrong type → `None`). TTL cache hit/expiry (injected clock). A private item skips a non-`private_ok` tool. An exception → `None`.

### A4 Acceptance tests first, RED (test-writer, M) | FR-01, FR-24, FR-33, FR-42, NFR-03
Files: `tests/integration/acceptance/{__init__,conftest,test_p1_school_erp,test_p2_approve_webhook,test_p3_crash_resume,test_p4_laya_down}.py`, `tests/helpers/{__init__,pipeline,receiver}.py`.
`helpers.pipeline.run_worker_until_idle(max_iters=20)` builds a `Worker` on the committed DB with the real `HANDLERS` and `prepare`. `helpers.receiver.WebhookReceiver` is a stdlib server thread that records requests and supports scripted status codes.
Each module starts with `pytest.importorskip("app.graph.run")` so B/C stay green. In group F they must run (not skip). Scenarios exactly as P1–P4.

### 1.1 Items API + ingest service (backend-builder, M) | FR-01, FR-02, FR-03, FR-06, FR-07
Files: `app/ingest/__init__.py`, `app/ingest/service.py`, `app/api/v1/items.py`, `tests/unit/ingest/test_sensitivity.py`, `tests/integration/test_items_api.py`.
Contracts: `async ingest_one(session, tenant_id, body: IngestItemIn) -> tuple[Item, bool]` does `INSERT … ON CONFLICT (tenant_id, source, source_ref) DO NOTHING RETURNING id`, then enqueues `process` in the same transaction. A repeat → existing item, `200`.
`raw` = payload untouched. `hints`/`callback_url` go to their columns. Sensitivity = `hints.sensitivity`, else `private` for `gmail|instagram|telegram|voice`, else the ADR 0005 default.
Bulk: one savepoint per row, `207`. Daily cap: count of today's (UTC) tenant items ≥ `items_per_day` → `429` + `Retry-After` until UTC midnight.
`GET /v1/items` with filters `status, niche, source, q` (ILIKE on `content->>'title'`) and cursor = last id (UUIDv7 desc), `limit ≤ 200`. `GET /v1/items/{id}` → `DecisionItemOut`, 404 for other tenants.
Scopes: `items:write` for POST, `items:read` for GET. Router only; wiring is in W.
Tests first: 202 then 200 on repeat; 207 with a mixed bulk; 501 rows → 422; the raw payload is byte-equal; job enqueued atomically; cap → 429; cursor paging; another tenant → 404.

### 1.2 Normaliser (pipeline-builder, M) | FR-10, FR-11, FR-12, FR-13
Files: `app/normalise/{__init__,service,llm_normaliser,language}.py`, `app/normalise/mappers/{__init__,hints,structured}.py`, `tests/unit/normalise/test_*.py`, `tests/unit/normalise/fixtures/`.
Contracts: C6. Mapper registry: `register_mapper(name)`, `map_payload(source, payload, hints) -> NormalisedContent | None`.
`hints` mapper: hints.title or hints.body present. `structured` mapper: a dict with title/subject + body/text/message/description, or a plain string (first line ≤ 120 → title).
LLM path: `gateway.complete_json("normalise", NormalisedContent, [system, user=fence(json payload, source)], sensitivity=item.sensitivity, item_id=…)`. On `LLMUnavailable` → title = `as_data(str(payload))[:120]` and `flags=["normalise_failed"]`.
Tests first: the school-ERP `{"text": …}` uses no LLM; an unknown payload calls `normalise` once; LLM failure → fallback, never raises; Gurmukhi/Devanagari/Hinglish/English detection; a private item passes `sensitivity="private"`.

### 1.5 Actions registry (pipeline-builder, M, after 1.2 in the same call) | FR-40, FR-41, NFR-07
Files: `app/actions/{__init__,registry,generic,jobs}.py`, `tests/unit/actions/test_registry.py`, `tests/integration/test_actions.py`.
Actions: `archive` (reversible), `label` (reversible, `{label: str ≤ 40}`), `snooze` / `remind` (`{until: datetime}` → enqueue `JobKind.ACTION` `{"op":"reminder_due","action_log_id"}` at `until`), `create_task` (`{title?, due?}` → result `{task}`), `webhook` (`{}`; delivers through the `action.done` event).
Phase 1 actions have no external side effects beyond events. `notify`, `draft_reply` and `send_reply` are not registered.
Tests first: same params twice → one `actions_log` row and the same result; different params → two rows; unknown → `unknown_action`; extra params → validation failure recorded as `failed`; `reminder_due` emits `action.done`.

### 1.3a Triage questions, modes, LLM fallback (laya-integrator, M) | FR-20, FR-21, FR-23, FR-24
Files: `app/triage/{questions,modes,fallback}.py`, `tests/unit/triage/test_questions.py`, `test_modes.py`, `test_fallback.py`.
Contracts: C5. Core questions per LAYA.md §2 (niche options = enabled niche descriptions, ≤ 12, keyed by name). Every question is validated against `laya_question.schema.json`.
`resolve_mode`: per-niche override `settings["laya_mode_by_niche"][niche]` > `settings["laya_mode"]` > env (default `shadow`). **Test: with no settings and the default env, the result is `shadow`.**
Fallback: `async classify(state, questions, *, sensitivity, item_id) -> dict[str, Answer]` via `gateway.complete_json("classify", <dynamic answers model>)`. A choice key outside the criteria → invalid. Probabilities = `{choice: c, others: (1-c)/(n-1)}`, `source="llm_fallback"`.
Tests first: 13 enabled niches → error (coarse-to-fine is out of scope; tell the owner); the fallback rejects an off-list key; a private item calls with `private`.

### 1.3b Triage service (laya-integrator, M) | FR-20..FR-25, NFR-03
Files: `app/triage/service.py`, `tests/unit/triage/test_service.py`, `tests/integration/test_triage_service.py`.
Rules:
- `off`: fallback only.
- `shadow`: Laya result → `shadow`; the fallback answers.
- `on`: Laya answers with `confidence ≥` the routed niche's `min_confidence`; the rest go to one fallback call for that subset.
- A hinted, enabled niche → `niche` answer `source="hint"`, and its niche questions go in the same Laya call. Otherwise one second call per niche group that has questions.
- `discard_if` and `risk=spam ≥ 0.85` → `discarded`. `scam_or_phishing ≥ 0.8` is stored on `items.risk`, and the graph enforces it.
- The fallback is needed but raises → `needs_human_triage` with `error="fallback_unavailable"`.
Tests first: 40 items → exactly one Laya call with 40 states; each mode; Laya `None` in shadow/on; Laya + LLM down → `needs_human_triage`; `item.triaged` emitted.

### 1.9 Feedback write + export (laya-integrator, S, after 1.3b in the same call) | FR-54, FR-80
Files: `app/feedback/{__init__,service,export}.py`, `tests/unit/feedback/test_export.py`, `tests/integration/test_feedback.py`.
Contracts: C8. `laya_train` line `{state, questions, gold: answers}`. `laya_eval` line `{state, questions, expected: {qid: key}}`. `since` filter. Streams with `yield_per`.
Tests first: one decision → one row; export lines match LAYA.md §6/§7; `state` ≤ 700 chars; no `raw` in the output.

### 1.6 Outbound webhooks (integration-builder, M) | FR-42, NFR-05
Files: `app/integrations/{webhooks_out,ssrf}.py`, `tests/unit/integrations/test_ssrf.py`, `test_envelope.py`, `tests/integration/test_webhooks_out.py`.
Contracts:
- `async handle_webhook_job(session, job)` handles two ops. `fanout`: creates one `webhook_deliveries` row (payload = envelope `{"event","id","created_at","data": item_to_public(...)}`) and one `deliver` job per subscription. `deliver`: decrypts the secret and POSTs the stored bytes with `X-DE-Signature: sign(secret, body)`, `X-DE-Event` and `X-DE-Delivery`. Timeout `webhook_timeout_seconds`; no redirects.
- 2xx → `delivered`. Otherwise `attempts+1`, then `next_attempt_at = now + RETRY_SCHEDULE_S[attempts-1]` with `(60, 300, 1800, 7200)`, and a new `deliver` job at that time. After 5 attempts → `failed` (dead-letter). The handler does not raise for HTTP failures, so the queue backoff does not stack on top.
- `check_url(url, *, allow_private) -> None` raises `UnsafeUrl`. It requires https unless `allow_private`, and blocks loopback, RFC 1918, link-local, 169.254.169.254, `::1`, ULA and multicast after DNS resolution. It is checked at subscribe time and at send time.
Tests first (respx + one real local receiver): signature verifies; retry schedule; dead-letter after 5; 3xx is not followed; private IP refused unless allowed; the secret never appears in logs.

### 1.8a `stack_catalog` tools + data (niche-designer, M) | FR-32, FR-71
Files: `/data/stacks.yaml` (~30 stacks: tags, skills, offline support, mobile, ₹ cost at small scale, `as_of`), `/data/free_tiers.yaml` (each entry `as_of` + source URL), `app/tools/stack_catalog.py`, `tests/unit/tools/test_stack_catalog.py`, and `/niches/tech_stack.yaml` / `/niches/generic.yaml` (only if the evals expose description overlap).
Contracts: `stack_catalog.shortlist` (args: `project_type, team_skills, budget_inr_month, offline_needed, languages_needed, users_expected`, all optional) → `ToolResult(data={"stacks": top ≤ 6 with score + reasons})`. `stack_catalog.free_tiers` (args: `budget_inr_month, project_type`) → entries with `as_of`. Both `private_ok=True` (local data), `ttl_s=3600`, path from `settings.data_dir`.
Tests first: offline + ₹0 + 3 devs ranks an offline-first stack (e.g. Expo + SQLite/PowerSync-class + free Postgres) in the top 3; every free tier has `as_of`; a missing data file → `None`, not a crash.

### 1.8b Evals (niche-designer, S) | FR-73
Files: `/evals/generic.jsonl`, `/evals/tech_stack.jsonl` (≥ 30 rows each per LAYA.md §6, balanced, Indian context, some hi/Hinglish, near-misses that belong to the other niche), `tests/unit/niches/test_evals_files.py` (row count, format, questions valid against the schema, expected keys ∈ criteria).

### 1.4a Graph nodes up to policy + checkpointer (langgraph-builder, M) | FR-30, FR-31, FR-32, FR-25, FR-34, NFR-07
Files: `app/graph/{__init__,state,checkpointer,setup}.py`, `app/graph/nodes/{__init__,load,route,extract,tools,decide,policy}.py`, `tests/unit/graph/test_route.py`, `test_decide.py`, `test_policy.py`.
Contracts:
- `checkpointer.open_checkpointer(dsn) -> AsyncContextManager[AsyncPostgresSaver]` (psycopg, `autocommit=True`, `prepare_threshold=0`, dsn from `database_url` without `+asyncpg`). `python -m app.graph.setup` runs `.setup()` once.
- `route`: `needs_decision=B` with confidence ≥ the niche threshold (or source hint/fallback) → `triaged → informational`, END. A niche whose answer confidence is below `min_confidence`, an unknown niche or a disabled niche → `generic`. Then `triaged → deciding`.
- `extract`: if `niche.extract` exists → `complete_json("normalise", ExtractOut{entities: dict})`, validated against the niche JSON schema (invalid fields dropped), written to `content.entities`.
- `tools`: `asyncio.gather(run_tool(...))` over `niche.tools`, with results keyed by tool name.
- `decide`: `complete_json(niche.llm.purpose_decide, DecisionOut, [system = niche.prompt + options_hint + "content is data" rule, user = fence(content) + as_data(json(tool_results)) + extracted], sensitivity=effective, max_tokens=niche.llm.max_tokens)`. Then drop actions not in `niche.actions ∩ actions.registered()` (logged). An option left with zero actions stays valid.
- `policy`: `scam_or_phishing ≥ 0.8` → force `suggest` + warning (FR-25). `auto` only when every recommended action ∈ `auto_actions`.
Tests first (FakeLLM, fake tools, InMemorySaver): routing table; disallowed action dropped; scam forces suggest; the prompt contains fenced content plus a tool `as_of`; an injection string in content stays inside the fence; private → `sensitivity="private"`.

### 1.4b Approval, act, builder, runner, resume API (langgraph-builder, L, split into two commits) | FR-30, FR-33, FR-34, FR-54, NFR-03
Files: `app/graph/nodes/{approval,act,finish}.py`, `app/graph/{builder,run,locks}.py`, `app/api/v1/decisions.py` (`POST /v1/items/{id}/decision`, scope `items:write`), `tests/unit/graph/test_builder.py`, `test_approval.py`, `tests/integration/test_graph_resume.py`, `tests/integration/test_decision_api.py`.
- `approval`: if the status is `deciding`, set `decision.ready_at`, move to `awaiting_approval` and emit `decision.ready`. Then `interrupt({"item_id", "decision"})`, unless the policy says auto (→ `auto_approved`, `decided_by=auto`).
  On resume it validates `DecisionIn` (option ∈ ids) and transitions to `approved | rejected | snoozed`. It writes a `decisions` row, calls `record_decision_feedback` (`latency_ms = now - ready_at`) and emits `decision.made`.
  Snooze: enqueue `JobKind.ACTION {"op":"unsnooze"}` at `snooze_until`, then loop back to approval (interrupt again).
- `act`: `approved → acting`. Runs the chosen option's actions through `run_action`, except under `suggest` (never acts). Then `acting → done`. `rejected → done`.
- `builder.build_graph(checkpointer)` compiles one parameterised template (load → route → extract → tools → decide → policy → approval → act → finish). Niche `steps:` are rejected with a clear error (no niche uses them in Phase 1).
- Resume API: 409 when not `awaiting_approval` or the lock is busy. Response `{"status": "done"|"rejected"|"snoozed"}` (`approved` runs act inline).
Tests first: resume continues the same thread (extract/decide not re-called); a double submit → one 200 + one 409; snooze → unsnooze → awaiting again; under `suggest` approve runs no actions; Postgres checkpointer round-trip.

### 1.7 `POST /v1/decide` (langgraph-builder, M, after 1.4b in the same call) | FR-35, FR-96
Files: `app/graph/oneshot.py`, `app/api/v1/decide.py` (scope `decide`), `tests/unit/graph/test_oneshot.py`, `tests/integration/test_decide_api.py`.
Contracts: body per API.md plus an optional `sensitivity` (ADR 0005). Questions are validated against the schema (≤ 16 questions).
State: `as_data(str | canonical JSON)`. One Laya call. `None` → `triage.fallback.classify` with `fallback: true`. When the fallback is unavailable → 503 problem.
`niche` → run the extract/tools/decide/policy functions with **no checkpointer and no DB writes** → `decision`. `explain` without `niche` → `explanation: str` (additive field) via `complete_text("decide")`.
`asyncio.timeout(decide_timeout_seconds)` → 504. Mode does not gate this endpoint (the caller asked for Laya answers), and the response says `fallback`.
Tests first: Laya ok → `fallback:false` with no LLM call; Laya down → fallback; timeout → 504; an invalid question → 422; a niche run writes no rows.

### P Pipeline wiring in the worker (pipeline-builder, M) | FR-20, NFR-02, NFR-03
Files: `app/workers/{handlers,run,pipeline}.py`, `tests/unit/workers/test_pipeline.py`, plus updates to `tests/integration/test_worker_flow.py` and `test_worker_lifecycle.py` (they assumed the Phase 0 stub).
Contracts: C9. `HANDLERS = {PROCESS: process_item, WEBHOOK: integrations.webhooks_out.handle_webhook_job, ACTION: dispatch(reminder_due → actions.jobs, unsnooze → graph.run.unsnooze_item)}`.
`process_item` takes `item_lock` around `run_item`. `Worker.run_forever` closes the graph checkpointer pool on stop.
Tests first: a claimed batch of 5 → one Laya call; the prepare hook failing → per-job handlers still finish; a process job for an `awaiting_approval` item is a no-op.

### W API wiring, routers, image, Makefile (backend-builder, M) | FR-42, FR-80, NFR-12
Files: `app/api/v1/__init__.py` (include items, decisions, decide, subscriptions, feedback), `app/api/v1/subscriptions.py` (GET/POST/DELETE, scope `admin`, secret Fernet-encrypted, `check_url` at create, secret never returned), `app/api/v1/feedback.py` (`GET /v1/feedback/export`, scope `admin`, `StreamingResponse` `application/x-ndjson`),
`app/main.py` (lifespan opens the checkpointer, `app.state.graph`), `docker-entrypoint.sh` (`alembic upgrade head && python -m app.graph.setup` before the api), `Dockerfile` (`COPY data/*.yaml`), `/Makefile` (`seed`, `eval`, `sdk`, `accept-phase1` targets), `tests/integration/test_subscriptions_api.py`, `tests/integration/test_feedback_api.py`, `tests/integration/test_openapi.py` (every route has tags and an example).
Tests first: subscription to `http://127.0.0.1` → 422 unless allowed; the secret is absent from GET; export streams JSONL.

### 1.9b Eval runner (laya-integrator, S) | FR-73
Files: `scripts/eval.py`, `tests/unit/triage/test_eval_runner.py`. `python -m scripts.eval --niche x` → Laya (if `LAYA_URL`) and the LLM fallback on `evals/x.jsonl`: accuracy, a simple 10-bin ECE, a confusion matrix, and a per-language slice. Exit 2 = skipped (neither Laya nor an LLM key).

### 1.10 SDKs (integration-builder, M) | FR-96, FR-111
*Blocked by ADR 0006.* Files: `scripts/export_openapi.py` (writes `/packages/openapi.json`), `/packages/client-py/` (generated by a pinned `openapi-python-client` via `uvx`, plus a thin `client.py` with retries and `verify_signature()` wrapping the same `t=,v1=` scheme), `/packages/client-ts/` (`openapi-typescript` types + `openapi-fetch` + `verifySignature.ts`, package.json + lockfile, README examples), `tests/unit/test_sdk_signature_compat.py` (Python verify accepts a server-signed body).
`make sdk` regenerates both. CI then checks `git diff --exit-code packages/`, a follow-up for devops-deployer in `/.github/workflows/ci.yml`.

### 1.11 Seed + live acceptance scripts (test-writer, S) | FR-01
Files: `scripts/seed.py` + `/data/seed/demo_items.jsonl` (50 items: about 15 tech_stack, 15 generic, and 20 shaped like inbox/news/agriculture/scam, all with `hints.title/body/language` so the normaliser uses no LLM; `source="seed"`, stable `source_ref` → idempotent), `scripts/accept_phase1.py`, `scripts/webhook_receiver.py`, `tests/integration/test_seed.py`.
Seed runs through `ingest_one` (no HTTP). `--limit N` (default 50) protects the free-tier budget.

---

## Parallel groups
One owner per file per group. `pyproject.toml`, `uv.lock`, `alembic/`, `tests/conftest.py`, `app/schemas/`, `app/api/v1/__init__.py`, `app/main.py` and `/Makefile` belong to **backend-builder only**. Others request changes in their report.

| Group | Runs | Steps (owner) | Depends on |
|---|---|---|---|
| **0** | alone | architect: ADR 0003–0006 + DATA_MODEL/API.md contract edits. Owner answers Q1–Q3 | none |
| **A** | ∥ | A1 (backend-builder) ∥ A2 (integration-builder) ∥ A3 (langgraph-builder) ∥ A4 (test-writer) | 0 |
| **B** | ∥ | 1.1 (backend-builder) ∥ 1.2 → 1.5 (pipeline-builder) ∥ 1.3a → 1.3b → 1.9 (laya-integrator) ∥ 1.6 (integration-builder) ∥ 1.8a → 1.8b (niche-designer) ∥ 1.4a (langgraph-builder) | A |
| **C** | alone | 1.4b → 1.7 (langgraph-builder) | B (actions registry, feedback service, triage fallback, stack_catalog) |
| **D** | ∥ | P (pipeline-builder) ∥ W (backend-builder) ∥ 1.9b (laya-integrator) | C |
| **E** | ∥ | 1.10 (integration-builder) ∥ 1.11 (test-writer) | D (final OpenAPI, ingest, Makefile targets) |
| **F** | sequential | test-writer (A4 green and not skipped, gap fill, `docs/TEST_MATRIX.md` Phase 1 rows) → code-reviewer → security-auditor (SSRF, webhook signing, prompt fences in normalise/extract/decide/classify, checkpoint contents, `callback_url`) → main session runs P1–P10, L1–L3 → docs-keeper (tick PLAN 1.1–1.11, API.md/DATA_MODEL.md/.env.example) | E |

Notes:
- 1.4a needs only C1 and C3, so it can run in B. The act node (needs C4) and the approval node (needs C8) are in C.
- A4's `importorskip` keeps B–D green. F fails the phase if any acceptance test is still skipped with a DB present.
- `tests/fakes/fake_laya.py` belongs to laya-integrator and `fake_llm.py` to llm-gateway-builder (unchanged). Nobody else edits them.

## Design decisions needing an ADR (architect, group 0)
1. **ADR 0003, LangGraph runtime.** New deps `langgraph`, `langgraph-checkpoint-postgres` and `psycopg[binary]` (a second Postgres driver and pool next to asyncpg).
   Checkpoint tables are created by `AsyncPostgresSaver.setup()` through `python -m app.graph.setup` in the entrypoint, **outside Alembic**. That is an exception to the CLAUDE.md "schema = migration" rule, and Alembic's `include_object` ignores those tables.
   Neon pooler URLs need `prepare_threshold=0` and `autocommit`. Graph state holds ids and derived data, not item content (a deviation from the ARCHITECTURE §3 `content` field, for retention and privacy). One parameterised template, with `steps:` deferred. Check the API image stays < 300 MB.
2. **ADR 0004, migration 0002 on `items`.** It adds `hints jsonb`, `callback_url text` and the `(tenant_id, created_at)` index.
   The alternative is a raw envelope `{payload, hints}` (no migration, but it bends FR-06). The FR-07 daily cap is counted **per tenant**, not per key, because `items` has no `api_key_id`.
   Per Q3, `callback_url` is stored but not delivered in Phase 1.
3. **ADR 0005, sensitivity defaults.** This decides the default for sources not in {gmail, instagram, telegram, voice}, whether decide/extract use `private` when *either* the item or the niche is private (that would send every `generic` item to a private provider, so with no Ollama they retry and then end `failed`), and the optional `sensitivity` field on `/v1/decide`. It encodes the owner's answer to Q2.
4. **ADR 0006, SDK toolchain.** `openapi-python-client` (pinned, via `uvx`, dev only) and the first Node package in the repo (`openapi-typescript`, `openapi-fetch`, and a package manager choice). The CI job additions are a devops follow-up.
5. **Contract fix (no new ADR, architect edits the docs).** FR-42 says `X-DE-Signature: sha256=<hmac>`, but API.md and the existing `security/hmac.py` use `t=<unix>,v1=<hex>`. Keep the implemented scheme and fix the FR-42 text.
   Also record the additive `items.triage` fields (`questions`, `shadow`, `source`, `error`), `items.decision` (`warnings`, `ready_at`, `niche_version`), `content.flags`, `/v1/decide` `explanation` and webhook delivery through `jobs(kind=webhook)` with its own 1 m/5 m/30 m/2 h schedule.

Settled defaults (stated so nobody re-litigates them): there is no `tool_cache` table yet (the in-process TTL cache meets FR-32 for local data; the table comes in Phase 7). Language detection uses script heuristics, with no new dependency.
Undo, retry, retriage and queue sorting wait for Phase 3. Items in `needs_human_triage` wait for the Phase 3 UI.

## Questions for the owner
1. **Enabled niches during Phase 1.** `news_radar` (autonomy `auto` archive) and `inbox` (private, needs Ollama) are `enabled: true`, so triage can route items to them before their phases.
   Default if you don't answer: set both to `enabled: false` until phases 2 and 4.
2. **Privacy default for your own API traffic.** Can items you POST from your own apps (`manual`, `webhook`, `radar`, `seed`) go to free-tier LLMs (Gemini/Groq) unless marked private? Default: yes (public). gmail, instagram, telegram and voice stay private.
   Without this, the school-ERP check needs Ollama or `hints.sensitivity=public`.
3. **Per-item `callback_url`.** Does any project need it in Phase 1? Default: it is accepted and stored but not delivered until Phase 2, and tenant subscriptions cover the acceptance check.

**Owner answers (2026-10-08), recorded by the architect:**
- **Q1:** `news_radar` and `inbox` get `enabled: false` until Phases 2 and 4 (niche-designer edits the YAML). Phase 1 enabled niches: `generic`, `tech_stack`.
- **Q2:** own-app sources (`manual`, `webhook`, `radar`, `seed`) default to `public`. `gmail`, `instagram`, `telegram`, `voice` stay `private`. `generic` does not force private routing (`generic.yaml` → `sensitivity: public`); an item's own `private` is never downgraded, and a private niche can raise a public item to private. `/v1/decide` gets an optional `sensitivity` (default `public`). See ADR 0005.
- **Q3:** `callback_url` is stored only in Phase 1; delivery in Phase 2. See ADR 0004.

Prerequisites for L1–L3 (not questions): a Gemini or Groq key, `TOKEN_ENC_KEY` and (dev only) `WEBHOOK_ALLOW_PRIVATE_URLS=true` in your `.env`. Docker with ≥ 6 GB for L3.

## Risks
- **Free-tier budget.** A tech_stack item costs about 3 LLM calls (classify fallback in shadow, extract, decide). `make seed` at 50 items is about 100–150 calls, roughly 30% of Gemini's 500 RPD. Seed uses hints to skip normalise and offers `--limit`.
- **Interrupt re-execution.** Code before `interrupt()` re-runs on resume. Every pre-interrupt side effect must be guarded by status (C7). This is a code-review focus.
- **Two drivers, two pools** (asyncpg + psycopg) double the idle connections on Neon free. Keep the psycopg pool `max_size=2` in the worker and 2 in the API.
- **DNS rebinding** on webhook URLs: `check_url` resolves at send time and the request must connect to the vetted IP. security-auditor verifies this.
- **Zero-shot Laya is weak** (LAYA.md §3.5), so shadow mode is mandatory. The `/v1/decide` consumers (radar) get raw Laya answers with confidences and should gate on them.
- **The 12-option limit** on the niche question: 5 starter niches today. A 13th enabled niche fails triage validation loudly (by design).
- **Size**: 1.4b is the largest step (L). It is split into two commits (approval+act+builder, then run+locks+route). If 1.3b passes about 400 lines, move the niche-question second call to its own commit.

## Out of scope (Phase 1)
Connectors and inbound webhooks (`/v1/webhooks/*`, Phases 2 and 5), `notify` / `draft_reply` / `send_reply` actions, Telegram/push, undo/retry/retriage endpoints and queue sorting (Phase 3),
uploads and Docling (Phase 5), pgvector dedupe (FR-15, Phase 2), few-shot corrections (FR-82, Phase 8), shadow report (FR-81, Phase 2), calibration, the niche wizard and DB niche overrides,
`callback_url` delivery (per Q3), the `tool_cache` table, custom niche `steps:`, FR-26 auto-archive of informational items, and any web or mobile code.

## Summary for the main session
- Steps: A1–A4 (contracts and RED acceptance tests), 1.1, 1.2, 1.3a/b, 1.4a/b, 1.5, 1.6, 1.7, 1.8a/b, 1.9, 1.9b, P, W, 1.10, 1.11, then the F review chain.
- Groups: 0 (architect ADRs 0003–0006 + owner Q1–Q3) → A (4 ∥) → B (6 ∥) → C (langgraph-builder alone) → D (3 ∥) → E (2 ∥) → F (sequential).
- Blockers: ADR 0003 (LangGraph deps), 0004 (migration), 0005 (sensitivity) before A1. ADR 0006 only blocks 1.10.
- Acceptance: P1–P4 integration tests (fakes) are the CI gate. L1–L3 are live and need an LLM key.
- First agent to call: **architect** (ADR 0003–0006), with the owner answering Q1–Q3 at the same time. Then group A.
