# Requirements

Numbered so code, tests and commits can cite them. **MUST** = MVP, **SHOULD** = before public launch,
**LATER** = after launch. Phase = the phase in `docs/PLAN.md` that delivers it.

## 1. Who it is for
| Persona | Need | First phase |
|---|---|---|
| **Owner (John)** | One place that tells him what needs a decision today across email, DMs, news, work apps; approve in seconds | 1–4 |
| **Other projects** | Opportunity Radar, Sarvam app, school ERP, farmer app call one API to get decisions | 1 |
| **Farmer (Punjab)** | Ask by voice in Punjabi: irrigate? spray? sell or hold? Get a short spoken answer with reasons | 7 |
| **Developer** | Describe a project, get a stack recommendation with trade-offs | 1 |
| **Public user (later)** | Sign up, connect sources, swipe decisions, no setup knowledge | 8 |

## 2. Functional requirements

### Ingestion
- **FR-01 MUST** `POST /v1/items` accepts one item `{source, source_ref, received_at?, payload, hints?}`; returns `202` with `id` and `status`.
- **FR-02 MUST** Idempotency: `(tenant, source, source_ref)` unique; a repeat returns the existing item with `200`, never a duplicate.
- **FR-03 MUST** `POST /v1/items/bulk` accepts up to 500 items in one call, partial success reported per row.
- **FR-04 MUST** `POST /v1/uploads` accepts CSV, JSONL or JSON (≤ 20 MB) plus a column mapping; rows become items through a job, with progress at `GET /v1/uploads/{id}`.
- **FR-05 SHOULD** Attachments (PDF, DOCX, images) are converted to text/markdown (Docling) and attached to the item.
- **FR-06 MUST** Every item stores the untouched raw payload (JSONB) so normalisation can be re-run.
- **FR-07 MUST** Rate limits with `429` + `Retry-After`: per API key 120 req/min (ADR 0002), and per tenant 5,000 new items per UTC day, a soft cap counted from persisted rows (ADR 0004).

### Normalisation ("anything to JSON")
- **FR-10 MUST** Every item is normalised to `schemas/decision_item.schema.json` (`content.title/body/sender/url/language/entities`).
- **FR-11 MUST** Already-structured payloads with a registered mapper (Gmail, RSS, Instagram, CSV mapping) are normalised without an LLM.
- **FR-12 MUST** Unknown payloads use the LLM gateway structured output (Pydantic model → JSON schema), validated; one repair retry; on failure the item keeps `title` = first 120 chars and is flagged `normalise_failed` (never dropped).
- **FR-13 MUST** Language detected (`en`, `hi`, `pa`, `hinglish`, other ISO code).
- **FR-14 SHOULD** Entities extracted per niche `extract` schema (dates, amounts, deadlines, crop, location, sender org).
- **FR-15 SHOULD** Near-duplicates (same story, forwarded email) linked via pgvector cosine ≥ 0.92 within 72 h; the duplicate becomes `related_to`, not a new decision.

### Triage (Laya)
- **FR-20 MUST** One Laya batch call per job batch answers the **core questions**: `needs_decision` (choice A/B), `niche` (choice over enabled niches, ≤ 12 options), `urgency` (score 0–2), `risk` (choice: normal / spam / scam_or_phishing).
- **FR-21 MUST** Each niche may add its own Laya questions (e.g. news `keep`), answered in the same call when the niche is known from hints, else in a second call after routing.
- **FR-22 MUST** Every answer stores choice, probabilities, confidence, model and Laya version on the item.
- **FR-23 MUST** Modes per tenant: `off`, `shadow` (record only; the LLM fallback decides), `on` (Laya decides when confidence ≥ niche threshold).
- **FR-24 MUST** Laya unavailable → LLM fallback classifier with the same questions and output shape; unavailable too → `needs_human_triage` queue. No item is lost.
- **FR-25 MUST** Items with `risk = scam_or_phishing` (conf ≥ 0.8) are never auto-actioned and show a warning banner.
- **FR-26 SHOULD** `needs_decision = no` items are auto-archived to "Done – informational" with undo, after the tenant opts in.

### Decision agents (LangGraph)
- **FR-30 MUST** A graph routes each triaged item to its niche subgraph; unknown/low-confidence → `generic`.
- **FR-31 MUST** A niche subgraph produces `decision.options[]` (2–5), `recommended`, `rationale` (≤ 3 sentences), `deadline?`, `actions[]` (from the niche allow-list), `confidence`.
- **FR-32 MUST** Niche tools come from a registry (`tools/`); a niche lists the tools it may call. Tool results are cached with TTL.
- **FR-33 MUST** Approval via LangGraph `interrupt()` with the Postgres checkpointer; resuming with approve / reject / edit / snooze continues the same thread.
- **FR-34 MUST** Autonomy per niche: `suggest` (never acts), `ask` (acts after approval), `auto` (acts without approval only for actions in `auto_actions`, shows in digest, 10 s undo where possible).
- **FR-35 MUST** `POST /v1/decide` synchronous one-shot: body has state + questions (Laya-style) and optional `explain: true`; returns Laya answers (+ LLM rationale when asked). Timeout 30 s.
- **FR-36 SHOULD** Rationale cites which inputs drove it (fields, tool results, data dates).

### Actions & outputs
- **FR-40 MUST** Action registry: `archive`, `label`, `snooze`, `remind`, `notify` (Telegram/push/email digest), `webhook` (call subscriber), `create_task`, `draft_reply` (never sends by itself), `send_reply` (approval only).
- **FR-41 MUST** Actions are idempotent (action key = item id + action + params hash) and logged with result.
- **FR-42 MUST** Outbound webhooks: tenants subscribe to events (`item.triaged`, `decision.ready`, `decision.made`, `action.done`); payload signed `X-DE-Signature: t=<unix>,v1=<hex hmac_sha256(secret, t + "." + body)>` (same scheme as FR-91, 5-min skew); retries 1 m/5 m/30 m/2 h then dead-letter.
- **FR-43 MUST** Telegram notifier: instant ping for urgency 2 within quiet-hours rules; daily digest at a set hour.
- **FR-44 SHOULD** Expo push notifications with action buttons (approve / reject).

### Approval queue (web + mobile)
- **FR-50 MUST** Queue of `awaiting_approval` items sorted by urgency then deadline then age; filters by niche/source.
- **FR-51 MUST** Card shows: source icon, one-line summary, recommended action, confidence chip, deadline, "why" (Laya top probabilities + rationale).
- **FR-52 MUST** Approve / reject / edit / snooze by button, keyboard (`a` `r` `e` `s`, `j`/`k`) and swipe (mobile: right approve, left reject, up snooze).
- **FR-53 MUST** Undo for 10 s after any queue action.
- **FR-54 MUST** Every queue action writes `feedback` (approved option or correction, time-to-decide).
- **FR-55 SHOULD** Bulk mode: select many low-urgency items, approve recommended for all.
- **FR-56 MUST** History: decided items, searchable, with what was done.

### Budgets, cost, models
- **FR-60 MUST** Per-provider daily request/token budgets (env-configurable), counted in Redis or Postgres, reset at provider reset time (UTC).
- **FR-61 MUST** Fallback order configurable; a provider returning 429/5xx is skipped for a cool-down.
- **FR-62 MUST** `llm_usage` table: provider, model, tokens, cost estimate, latency, purpose, item id.
- **FR-63 MUST** Sarvam used for Indic STT/translation/TTS and Indic text generation when language ∈ {hi, pa, …}.
- **FR-64 SHOULD** Cost dashboard: today vs budget per provider; alert at 80 %.

### Niches
- **FR-70 MUST** Niche YAML loaded at boot and on `POST /v1/niches/reload`; invalid YAML refuses to load with a clear error and keeps the previous version.
- **FR-71 MUST** Starter niches: `generic`, `tech_stack`, `news_radar`, `inbox`, `agriculture`.
- **FR-72 SHOULD** Niche wizard: `POST /v1/niches/draft {description}` → LLM drafts YAML (questions, extract schema, prompt, actions) → user edits in UI → saved to DB (overrides YAML) after schema validation.
- **FR-73 SHOULD** Each niche ships `evals/<niche>.jsonl` (≥ 30 labelled examples) and `make eval NICHE=x` reports Laya accuracy/ECE and LLM agreement.

### Learning loop
- **FR-80 MUST** Export feedback as Laya training JSONL (`{state, questions, gold}`) and eval JSONL (`{state, questions, expected}`) per niche.
- **FR-81 MUST** Shadow report: per niche and cutoff, how many items Laya would have decided and how many it would have got wrong vs human/LLM label.
- **FR-82 SHOULD** Few-shot memory: the last N human corrections per niche are injected into that niche's LLM prompt.
- **FR-83 LATER** Fine-tuned Laya checkpoint per tenant selected via `LAYA_MODEL` / request `model`.

### Connectors (details in docs/CONNECTORS.md)
- **FR-90 MUST** RSS/Atom + Google News queries + Hacker News (news_radar).
- **FR-91 MUST** Generic inbound webhook `POST /v1/webhooks/{source_slug}` with per-source HMAC secret.
- **FR-92 MUST** Gmail (OAuth, Testing mode, read-only first; history polling every 5 min; Pub/Sub push SHOULD).
- **FR-93 SHOULD** Instagram professional-account DMs via official webhooks (`messages`), reply drafts only inside the 24 h window.
- **FR-94 MUST** Telegram bot as input (forward anything to it → item) and as notifier.
- **FR-95 SHOULD** Voice notes (Telegram/WhatsApp/mobile) → Sarvam STT → item, original audio reference kept.
- **FR-96 MUST** Opportunity Radar bridge: radar can POST its scored items, or call `/v1/decide`, and share the same Laya service.
- **FR-97 LATER** WhatsApp Cloud API, Outlook, Slack, Google Calendar (create event action).

### Agriculture (phase 7)
- **FR-100 MUST** Tools: Agmarknet mandi prices (data.gov.in), Open-Meteo 7-day forecast, crop calendar table (PAU-sourced, versioned), farmer profile (crop, sowing date, village, land size).
- **FR-101 MUST** Decisions: irrigate now/wait, sell now/hold N days/sell at mandi X, pest/disease → "see expert" with photo, fertiliser timing (no doses without expert review).
- **FR-102 MUST** Answers in the farmer's language (pa/hi) as short text + optional TTS, with data date.
- **FR-103 MUST** Every advisory logged with the inputs used; expert review queue for flagged ones.

### Accounts & tenancy
- **FR-110 MUST** Single tenant at MVP; all tables carry `tenant_id` from day one.
- **FR-111 MUST** API keys (hashed, prefix shown), scopes: `items:write`, `items:read`, `decide`, `admin`.
- **FR-112 MUST** Web login: Auth.js with Google, allow-listed emails (`ALLOWED_EMAILS`).
- **FR-113 LATER** Self-serve signup, plans, usage metering, per-tenant Laya checkpoints.

## 3. Non-functional requirements
- **NFR-01 Latency**: `/v1/items` p95 < 300 ms (enqueue only). Triage p95 < 2 s per 32-item batch on CPU. `/v1/decide` without LLM p95 < 1.5 s.
- **NFR-02 Throughput**: 5,000 items/day on the free profile; worker batches of up to 32 items.
- **NFR-03 Availability**: degrade, never drop. Any dependency down → item waits or goes to human queue; jobs retried with backoff (5 tries, then `failed` visible in UI with "retry").
- **NFR-04 Cost**: runs at ₹0/month on free tiers for one user; every paid switch is an env change.
- **NFR-05 Security**: OWASP ASVS L1; secrets in env only; API keys hashed (argon2/sha256+pepper); webhooks HMAC with timestamp (5-min skew); CORS allow-list; OAuth tokens encrypted at rest (Fernet, `TOKEN_ENC_KEY`).
- **NFR-06 Privacy**: private items never leave to non-`private_ok` providers; logs hold ids only; "delete my data" endpoint (LATER); retention default 180 days for raw payloads.
- **NFR-07 Prompt-injection safety**: content is fenced as data; tool calls validated against the niche allow-list; no action derives a URL/email address from model text unless it already appears in the item.
- **NFR-08 Observability**: structured JSON logs with `item_id`, `job_id`, `trace_id`; `/health` and `/health/deep` (DB, Redis, Laya, one LLM ping cached 5 min); Prometheus-style `/metrics` SHOULD; LangSmith optional via env.
- **NFR-09 Testability**: core logic pure and unit-tested; coverage ≥ 80 % on `triage`, `graph`, `llm`, `security`, `actions`.
- **NFR-10 Accessibility**: WCAG 2.2 AA; full keyboard use; swipe always has a button alternative; min touch target 44 px; farmer mode font ≥ 18 px.
- **NFR-11 i18n**: en, hi, pa UI; RTL not needed; numbers ₹ and lakh formatting in `en-IN`.
- **NFR-12 Portability**: one `docker compose up` runs everything locally; no vendor lock-in beyond swappable env.
- **NFR-13 Scalability path**: stateless API/workers (horizontal); Laya behind a URL (move to GPU without code change); Postgres partition `items` by month after 5 M rows (LATER).
