# Build plan

Each phase is shippable on its own. Run it with `/build-phase N`. A phase is done only when every box
is ticked, its **acceptance** checks pass, and `make test` + `make lint` are green.
Owner = the `.claude/agents/` agent that builds it. Agents marked ∥ can run in parallel.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

---

## Phase 0 — Foundations (week 1)
Goal: a running skeleton where an item can be stored, a job claimed, Laya and an LLM called.

- [ ] 0.1 Monorepo scaffold: `apps/api` (uv, pyproject, ruff, mypy, pytest), `Makefile`, `.gitignore`, `.editorconfig`, pre-commit — **backend-builder**
- [ ] 0.2 `core/config.py` with every env var from `.env.example`; `core/logging.py` JSON logs — **backend-builder**
- [ ] 0.3 Postgres + pgvector via Alembic: `tenants, api_keys, sources, items, jobs, niches, decisions, feedback, llm_usage, actions_log, webhook_subscriptions, webhook_deliveries, tenant_settings` (docs/DATA_MODEL.md) — **backend-builder**
- [ ] 0.4 Job queue: `workers/queue.py` (enqueue, claim with SKIP LOCKED, retry/backoff, LISTEN/NOTIFY wake-up), `workers/run.py` — **pipeline-builder** ∥
- [ ] 0.5 API keys + auth dependency + rate limit; `GET /health`, `/health/deep` — **backend-builder**
- [ ] 0.6 `services/laya/Dockerfile` + `triage/laya_client.py` (HTTP, batching ≤ 32, timeout, None on failure) + fake for tests — **laya-integrator** ∥
- [ ] 0.7 `llm/gateway.py` with LiteLLM router, `providers.yaml`, budgets, cool-downs, privacy routing, `complete_json` with repair retry, `llm_usage` logging + fake — **llm-gateway-builder** ∥
- [ ] 0.8 Niche loader + JSON-schema validation of `niches/*.yaml`; `POST /v1/niches/reload` — **niche-designer**
- [ ] 0.9 `docker-compose.yml` (db, redis, api, worker, laya profile) + `.github/workflows/ci.yml` (lint, test with postgres service) — **devops-deployer** ∥
- [ ] 0.10 `security/untrusted.py` (`as_data`), `security/hmac.py`, `security/crypto.py` — **security-auditor** writes tests first, **backend-builder** implements

**Acceptance**: `make dev` starts everything; `curl /health/deep` all green (Laya may be `skipped` if profile off);
inserting an item creates a job the worker claims and marks `normalised` (stub); gateway fake + real Gemini
smoke test (`make smoke-llm`) returns valid JSON; Laya smoke (`make smoke-laya`) returns probabilities.

## Phase 1 — Core pipeline + first niches without connectors (weeks 2–3)
Goal: `POST /v1/items` or `/v1/decide` → a real decision waiting for approval via API.

- [x] 1.1 `POST /v1/items`, `/bulk`, `GET /v1/items`, `GET /v1/items/{id}` (FR-01..03, FR-06) — **backend-builder** (21e4ea3; A1: 6114340, 54f6eb2; fix 93341d9)
- [x] 1.2 Normaliser: mapper registry + LLM normaliser + language detection (FR-10..13) — **pipeline-builder** (be20e68)
- [x] 1.3 Triage service: core questions from enabled niches, one Laya batch, store answers, modes off/shadow/on, LLM fallback classifier, `needs_human_triage` (FR-20..25) — **laya-integrator** (1.3a: 652539b, 1.3b: ab0e5f3)
- [x] 1.4 Graph: state, builder from YAML, generic subgraph, policy, `interrupt()` approval, Postgres checkpointer, resume API `POST /v1/items/{id}/decision` (FR-30..34) — **langgraph-builder** (1.4a: b1128a9, 1.4b: 2b4a121, 7833838)
- [x] 1.5 Actions registry with `archive`, `label`, `snooze`, `remind`, `webhook`, `create_task` + idempotency log (FR-40, 41) — **pipeline-builder** (90499d1)
- [x] 1.6 Outbound webhooks + signing + retries (FR-42) — **integration-builder** (5764408; A2 event emitter: 6d72497)
- [x] 1.7 `POST /v1/decide` sync (FR-35) — **langgraph-builder** (2826012)
- [x] 1.8 Niches `generic` + `tech_stack` (tool: `stack_catalog` from `data/stacks.yaml`) with evals (≥ 30 rows each) — **niche-designer** (1.8a: f1f2e26, 1.8b: 7f802dc; eval runner 1.9b: 7da31d9)
- [x] 1.9 Feedback write on every decision + export JSONL (FR-54, FR-80) — **laya-integrator** (c71728b)
- [x] 1.10 Python + TS client SDKs from OpenAPI (`packages/`) — **integration-builder** (631f40e)
- [x] 1.11 `make seed` loads 50 demo items across niches — **test-writer** (d18870a; worker wiring P: c0d3bdc; API wiring W: db6155b, ed47a2d)

**Acceptance**: posting "Building a school ERP, 3 devs, offline mobile needed, ₹0 budget" returns a
`tech_stack` decision with options and rationale in `awaiting_approval`; approving it fires a signed webhook
received by a test server; worker crash mid-graph resumes from checkpoint; Laya down → fallback path used,
no item lost (integration test).

## Phase 2 — News radar niche + Telegram (weeks 3–4)
Status (uncommitted, 2026-10-14): code and tests in the working tree; acceptance not run yet.
Open: 2.1 cron for `python -m app.connectors.schedule`; 2.2 `news_radar` still `enabled: false`
and pgvector dedupe not built; 2.4 notifier pass built and scheduled in compose, but not yet run against a real chat; 2.5 radar side
not wired; 2.6 needs real feedback rows before it prints numbers. Tick `[x]` with the commit hash.
Goal: daily AI/crypto/news keep-or-skip with a Telegram digest; Opportunity Radar can plug in.

- [~] 2.1 RSS/Atom, Google News query, Hacker News connectors as pollers (FR-90) — **connector-builder**
- [~] 2.2 `news_radar` niche: Laya `keep` question per topic, interest profile from tenant settings, LLM summary only for keeps, dedupe by pgvector (FR-15) — **niche-designer** + **laya-integrator**
- [~] 2.3 Starter feed lists per topic (ai, crypto, india_tech, punjab_agri_policy) — **feed-scout**
- [~] 2.4 Telegram bot: input (forward → item), notifier (urgent ping, daily digest, approve/reject buttons) (FR-43, FR-94) — **connector-builder**
- [~] 2.5 Opportunity Radar bridge: docs + example `radar_bridge.py` posting to `/v1/items` with `hints.niche=news_radar`; shared Laya service (FR-96) — **integration-builder**
- [~] 2.6 Shadow report `python -m app.feedback.shadow_report` (FR-81) — **laya-integrator**

**Acceptance**: 24 h run on 10 feeds produces ≤ 15 kept stories, a digest at the set hour, buttons work;
shadow report prints per-cutoff missed/skipped table.

## Phase 3 — Web app: approval queue (weeks 4–6)
Status (uncommitted until noted, 2026-10-14): 3.1–3.3 partly built, see the boxes below.
- [~] 3.1 UX spec + design tokens + screen mocks per docs/UI_UX.md — **ui-ux-designer** (tokens in `globals.css`; queue states in UI_UX.md section 8; mocks not drawn)
- [~] 3.2 Next.js app scaffold, Auth.js Google + allow-list, server-side API proxy, i18n (en/hi/pa) — **frontend-builder** (live Google sign-in not run: no OAuth client here; shadcn/ui not added yet)
- [~] 3.3 Queue screen with cards, keyboard shortcuts, undo toast, bulk mode (FR-50..55) — **frontend-builder** (cards, keys, undo, option choice done; snooze, edit, bulk, filter chips, command palette not yet)
- [ ] 3.4 Item detail: raw vs normalised, Laya probabilities, rationale, edit decision — **frontend-builder**
- [ ] 3.5 History, Niches (view/edit YAML with validation), Sources (add RSS/webhook), Insights (budgets, counts), Settings (Laya mode, autonomy, digest hour, quiet hours) — **frontend-builder**
- [ ] 3.6 Playwright e2e: approve flow, keyboard flow, undo — **test-writer**
- [ ] 3.7 UX review against checklist + screenshots fixes — **ui-ux-designer**

**Acceptance**: Lighthouse a11y ≥ 95; full queue usable with keyboard only; approve → done in one keypress.

## Phase 4 — Personal inbox (weeks 6–8)
- [ ] 4.1 Gmail OAuth (Testing mode), encrypted token storage, history polling, Gmail mapper (FR-92) — **connector-builder**
- [ ] 4.2 `inbox` niche: needs-reply, category, deadline extraction, draft reply (private → Ollama/allowed provider) — **niche-designer**
- [ ] 4.3 Gmail actions: label, archive, create draft (never send without approval) — **connector-builder**
- [ ] 4.4 Ollama provider in gateway, `private_ok` routing test — **llm-gateway-builder**
- [ ] 4.5 Security audit of OAuth, token storage, prompt injection via email bodies — **security-auditor**

**Acceptance**: 1 week on the owner's inbox: promos auto-archived only after opt-in; every reply is a draft in Gmail; no email body in logs; no private item sent to a non-`private_ok` provider (test + log check).

## Phase 5 — Instagram, generic webhooks, bulk uploads, attachments (weeks 8–9)
- [ ] 5.1 Instagram (professional account) webhook + DM mapper + reply-draft within 24 h window (FR-93) — **connector-builder**
- [ ] 5.2 Generic inbound webhook sources with per-source HMAC (FR-91) — **connector-builder**
- [ ] 5.3 Uploads: CSV/JSONL/JSON + mapping UI + progress (FR-04) — **backend-builder** + **frontend-builder**
- [ ] 5.4 Docling attachment conversion (FR-05) — **pipeline-builder**

## Phase 6 — Mobile app (weeks 9–11)
- [ ] 6.1 Expo app: login (device token via QR from web), swipe queue, detail, history, settings — **mobile-builder**
- [ ] 6.2 Push notifications with approve/reject actions (FR-44) — **mobile-builder**
- [ ] 6.3 Farmer mode UI (large type, voice button, pa/hi) — **mobile-builder** + **ui-ux-designer**
- [ ] 6.4 EAS build profiles; internal testing release — **devops-deployer**

## Phase 7 — Agriculture pilot (weeks 11–14)
- [ ] 7.1 Tools: Agmarknet, Open-Meteo, crop calendar (PAU sourced, versioned YAML), farmer profile (FR-100) — **agri-domain-expert**
- [ ] 7.2 `agriculture` niche + Punjabi/Hindi evals (FR-101) — **agri-domain-expert** + **niche-designer**
- [ ] 7.3 Voice in/out with Sarvam STT/TTS + translation (FR-95, FR-102) — **llm-gateway-builder**
- [ ] 7.4 Expert review queue + advisory log (FR-103) — **frontend-builder**
- [ ] 7.5 Safety review of all advisory prompts and outputs — **security-auditor** + **agri-domain-expert**

**Acceptance**: 5–10 farmers near Jalandhar, 2 weeks; every chemical-related answer went through expert review; answers carry data date.

## Phase 8 — Learning loop, niche wizard, launch prep (weeks 14+)
- [ ] 8.1 Laya calibration (temperature fit on feedback) + switch niches from shadow to on per report — **laya-integrator**
- [ ] 8.2 Fine-tune export + Kaggle notebook guide + eval gate before using a new checkpoint (FR-83) — **laya-integrator**
- [ ] 8.3 Few-shot corrections in prompts (FR-82) — **langgraph-builder**
- [ ] 8.4 Niche wizard (FR-72) + UI — **niche-designer** + **frontend-builder**
- [ ] 8.5 Multi-tenant hardening, signup, usage metering (FR-113) — **architect** → **backend-builder**
- [ ] 8.6 Paid-tier deploy (no spin-down, Laya VM, paid LLM primary) — **devops-deployer**
- [ ] 8.7 Full security audit + privacy policy + data deletion — **security-auditor**

---
## Definition of done (every task)
1. Code + tests (unit for logic, integration for API/DB) — failing test first for bugs.
2. `make lint` and `make test` green; no new `# type: ignore` without a reason.
3. Requirement ids cited in tests or docstrings.
4. Docs touched where behaviour changed (API.md, NICHES.md, .env.example).
5. code-reviewer has no blocking findings.
6. Box ticked here by docs-keeper, with the commit hash.
