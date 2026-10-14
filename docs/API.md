# HTTP API (v1)

Base: `https://<host>/v1`. JSON in and out (UTF-8). OpenAPI at `/openapi.json`, docs at `/docs`.
Auth: `Authorization: Bearer de_<prefix>_<secret>` (API key, scoped). Errors: RFC 9457
`application/problem+json` `{type, title, status, detail, errors?}`.
Pagination: cursor (`?cursor=<opaque>&limit=50`, max 200) → `{data: [...], next_cursor}`.

**Request size (NFR-05).** A body over `MAX_REQUEST_BYTES` (default 1,048,576) → `413` problem+json, and
`POST /v1/items/bulk` allows `MAX_BULK_REQUEST_BYTES` (default 10,485,760) instead. The server checks
`Content-Length` first, then counts streamed bytes, so an oversized body is cut off without being buffered.
The `413` is added by middleware, so it is not listed in `/openapi.json`. Its `type` is `about:blank`.

## Status: what is built today
Checked against `apps/api/app/api/v1/*.py` and `apps/api/app/schemas/settings.py` (2026-10-14).

- **Built:** `POST /v1/items`, `POST /v1/items/bulk`, `GET /v1/items`, `GET /v1/items/{id}`,
  `GET /v1/items/{id}/activity`, `POST /v1/items/{id}/decision`, `POST /v1/decide`,
  `GET /v1/settings`, `PUT /v1/settings` (five fields only), `POST /v1/niches/reload`,
  `POST|GET|DELETE /v1/subscriptions`, `GET /v1/feedback/export`, `POST /v1/telegram/webhook`,
  `GET /health`, `GET /health/deep`.
- **PLANNED (Phase 3 step 3.5-B, not built yet):** the Laya mode fields in Settings, the Niches
  list/get/put routes, the Sources routes, and `GET /v1/stats/today`. Each one is marked below.
- **NOT BUILT (no route yet):** `POST /v1/items/{id}/undo` (LATER, ADR 0007), `POST /v1/items/{id}/retry`,
  `POST /v1/items/{id}/retriage`, `POST /v1/uploads`, `GET /v1/feedback/shadow-report`, inbound
  `POST /v1/webhooks/{source_slug}`, and the sources OAuth routes.

Text under a **PLANNED** or **NOT BUILT** label is the target contract. Clients must not call it until the route ships.

## Items
### `POST /v1/items` — scope `items:write` (FR-01, FR-02)
```json
{
  "source": "webhook",                     // gmail | instagram | rss | webhook | csv | telegram | voice | manual | radar | <slug>
  "source_ref": "order-8812",              // unique per source; used for idempotency
  "received_at": "2026-10-07T08:30:00Z",   // optional, default now
  "payload": { "any": "json" },            // raw; stored untouched
  "hints": {                               // optional; skip work when you already know
    "niche": "news_radar",
    "language": "en",
    "sensitivity": "public",               // public | private. Default by source (ADR 0005): public for manual/webhook/
                                           // radar/seed (and rss); private for gmail/instagram/telegram/voice and any other source
    "title": "…", "body": "…", "url": "…", "sender": "…"
  },
  "callback_url": "https://my-app/decision-hook"   // optional; https only. STORED, NOT YET DELIVERED (Phase 2, ADR 0004)
}
```
`202 {"id": "0192…", "status": "new"}` · repeat → `200` same body · `422` validation · `429` rate limit.
`hints` and `callback_url` are stored in their own columns and never returned by any GET or webhook (ADR 0004).

**Rate limits (FR-07).** Per API key: 120 req/min → `429` + `Retry-After` (ADR 0002). Per tenant: 5,000 new items per
UTC day, checked once per request before inserting. When today's count is already at the cap → `429`
problem+json `{"type": "https://decision-engine/problems/daily-item-cap", "title": "Daily item cap reached", "status": 429}`
with `Retry-After` = seconds until 00:00 UTC. It is a soft cap: an accepted bulk call may overshoot (ADR 0004).

### `POST /v1/items/bulk` (FR-03)
`{"items": [ <item>, … ≤500 ]}` → `207 {"results": [{"index":0,"id":"…","status":"new"}, {"index":1,"error":"source: Field required"}]}`
A failed row carries `error` as a short `field: message` string (first validation error); the other rows are unaffected.

### `GET /v1/items?status=awaiting_approval&niche=inbox&source=gmail&q=text&cursor=…`
### `GET /v1/items/{id}` → full DecisionItem (schemas/decision_item.schema.json)
### `GET /v1/items/{id}/activity` — built (scope `items:read`)
→ `{"data": [{"action", "status", "created_at", "reversible", "undone_at"}]}`, newest first, capped at the server limit.
`404` for an unknown item or another tenant's item.
### `POST /v1/items/{id}/decision` — resume the approval interrupt (FR-33)
```json
{ "verdict": "approve",                 // approve | reject | edit | snooze
  "option": "B",                        // optional: choose a non-recommended option
  "edits": { "reply_draft": "…" },      // for edit
  "snooze_until": "2026-10-08T03:30:00Z",
  "note": "too expensive" }             // free text, stored in feedback
```
→ `200 {"status":"done"|"snoozed"|"rejected"}` (`approve`/`edit` run the allowed actions inline and return `done`;
under `suggest` autonomy no action runs; `rejected` reports the verdict, the item itself ends `done`). Clients must
also accept `"acting"`, reserved for long-running actions in later phases.
`422` when `option` is not an option id, or `snooze` lacks a future `snooze_until`. `404` for another tenant's item.
`409` problem+json when the item is not `awaiting_approval` **or** another request/worker holds the item
(`type: .../not-awaiting-approval` or `.../item-busy`). A double submit gives one `200` and one `409`.
### `POST /v1/items/{id}/undo` — LATER, not built (ADR 0007)
FR-53 undo is a client-side hold: queue clients keep a decision for 10 s and only then send one
`POST /v1/items/{id}/decision`. Undo inside the window sends nothing. A `409` after the window means another client
already handled the item.
### `POST /v1/items/{id}/retry` — NOT BUILT yet — failed items
### `POST /v1/items/{id}/retriage` — NOT BUILT yet — rerun normalise+triage (after a niche change)

## Synchronous decisions
### `POST /v1/decide` — scope `decide` (FR-35)
```json
{
  "state": "text or JSON object to decide about",
  "questions": {                                         // Laya format (docs/LAYA.md)
    "sell": {"type": "choice", "instructions": "Sell the wheat now or hold?",
             "criteria": {"A": "sell now", "B": "hold 1-2 weeks", "C": "hold > 2 weeks"}}
  },
  "niche": "tech_stack",           // optional: also run that niche's tools + LLM decision
  "explain": true,                 // optional: LLM rationale
  "language": "pa",                // optional: answer language for rationale
  "sensitivity": "public"          // optional, default public (ADR 0005); private → only private_ok providers
}
```
→ `200 {"answers": {"sell": {"choice":"B","probabilities":{…},"confidence":0.71}}, "decision": {…}?, "explanation": "…"?, "shadow": {…}?, "model": "laya-english", "fallback": false}`
- **Laya mode.** This endpoint honours the server's `LAYA_MODE` (default `shadow`). Per-tenant and per-niche
  overrides are not read here yet, so the server default applies to every call.
  - `shadow` (default): the answers come from the LLM fallback classifier. Laya's answers are returned only in
    `shadow`, and are never used as the answer.
  - `on`: Laya answers at or above the confidence gate are used. The rest go to the LLM fallback. The gate is the
    niche's `triage.min_confidence` when `niche` is set, otherwise 0.75.
  - `off`: Laya is not called. All answers come from the LLM fallback.
- `shadow` (additive, `null` when absent): `{"answers": {…} | null, "model": "…" | null, "latency_ms": null, "error": null}`.
  It is `null` when Laya gave no usable answer. This endpoint sets only `answers` and `model`; `latency_ms` and
  `error` are filled by triage, not here.
- `fallback: true` when at least one answer came from the LLM fallback classifier. In `shadow` and `off` modes
  this is true whenever `questions` is non-empty.
- `decision` only with `niche` (runs extract/tools/decide/policy; writes nothing). One-shot autonomy is always
  `suggest` and `warnings` carries `"one-shot: no scam screening"` (no triage risk is available). A private niche forces
  private routing even when `sensitivity` is `public`. `explanation` (additive) is returned whenever `explain` is true,
  with or without `niche`.
- **Daily cap.** Each tenant gets `DECIDE_DAILY_LIMIT_PER_TENANT` calls (default 500) per UTC day. Calls past
  the limit get `429` problem+json `{"type": "https://decision-engine/problems/daily-decide-cap",
  "title": "Daily decide cap reached", "status": 429}` with `Retry-After` = seconds until 00:00 UTC. The cap is
  counted before the answer, so a call that passes body validation uses a slot even if it later returns `422`
  or `503`. The per-key rate limit (`RATE_LIMIT_PER_MIN`, 120/min) also returns `429` + `Retry-After`.
- Errors: `422` invalid questions (schema, ≤ 16 questions) or unknown or disabled niche · `413` body over
  `MAX_REQUEST_BYTES` · `429` daily cap or rate limit (see above) · `503` fallback needed but unavailable, or
  private with no `private_ok` provider (`type: .../no-private-provider`) · `504` after `DECIDE_TIMEOUT_SECONDS`
  (default 30).

## Uploads (FR-04)
**NOT BUILT yet.** No `/v1/uploads` route exists. The contract below is the target.

`POST /v1/uploads` multipart `file` + `mapping` JSON:
```json
{"source": "csv", "source_ref_column": "id", "title": "subject", "body": "message",
 "sender": "from", "received_at": "date", "niche_hint": "inbox", "sensitivity": "private"}
```
→ `202 {"upload_id": "…"}` · `GET /v1/uploads/{id}` → `{status, total, done, failed, errors:[…≤50]}`

## Settings (FR-43, FR-23; ADR 0008)
**Built today:** the five fields below. Nothing else.
- `GET /v1/settings` scope `items:read` → `SettingsOut` (the five fields).
- `PUT /v1/settings` scope `admin`. Body `SettingsIn` (`extra` keys → `422`). It merges into the stored settings and
  keeps keys it does not own. A request that sends `laya_mode` today gets `422`, because the key is unknown.
```json
{ "quiet_hours": [22, 7], "digest_hour": 8, "ping_cap_per_day": 3, "interests": ["ai"], "languages": ["en"] }
```
→ `200 SettingsOut` (the same five fields).
- `422` (`errors[{field, message, code}]`): out-of-range values, or any unknown key.

**PLANNED (Phase 3 step 3.5-B, not built yet): Laya mode fields (step 3.5-B4, ADR 0008).** Not live. The fields
below are the target contract. `triage/modes.resolve_mode` already reads the stored keys, but this API cannot write them yet.
```json
{ "laya_mode": "shadow",                        // optional; "off"|"shadow"|"on"|null. Absent = unchanged, null = use env LAYA_MODE
  "laya_mode_by_niche": {"news_radar": "off"} } // optional; full replacement of the map (≤ 50); absent = unchanged
```
→ `200 SettingsOut` would add `laya_mode` (stored value or `null`), `laya_mode_by_niche` (stored map) and
`laya_mode_default` (env `LAYA_MODE`, read-only).
- Planned `422`: unknown niche in the map (`code: unknown_niche`). A change **to** `on` → `type:
  https://decision-engine/problems/laya-mode-gated`, `code: laya_mode_gated`. `on` is accepted only as an unchanged
  re-send of the stored value; going to `on` needs the LAYA.md §5 gate and an ADR. `on` → `off`/`shadow` is always allowed.

## Niches (FR-70, FR-72; ADR 0009, ADR 0011)
**PLANNED (Phase 3 step 3.5-B, not built yet).** The list, get and put routes below are not live.
**Built today:** `POST /v1/niches/reload` only. It reloads the YAML files. The DB overrides are not read yet.

- **PLANNED (Phase 3 step 3.5-B, not built yet): `GET /v1/niches`** scope `items:read` → `{"data": [{"name", "label",
  "description", "enabled", "autonomy", "auto_actions", "source": "yaml"|"db", "version", "laya_mode"}]}`.
  `laya_mode` is the effective mode (read-only).
- **PLANNED (Phase 3 step 3.5-B, not built yet): `GET /v1/niches/{name}`** scope `items:read` → `{"name", "source", "version", "config":
  {…effective…}, "yaml": "…"}` (`yaml` is the file text, or a dump of the DB config). `404` unknown name.
- **PLANNED (Phase 3 step 3.5-B, not built yet): `PUT /v1/niches/{name}`** scope `admin`. Body = one complete niche config as a JSON object.
  It replaces the YAML niche of that name in the DB (no merge). The server sets `version`. → `200` same shape as GET.
  Every process sees it on its next unit of work.
  `422` problem+json `{"title": "Niche validation failed", "errors": [{"json_pointer", "message"}]}` (all schema errors,
  sorted, ≤ 20; nothing is saved) for: schema violations; `/name` ≠ path; `generic` with `/enabled` false; non-empty
  `/steps`; an unregistered `/actions/i` or `/tools/i` **that this PUT adds** relative to the effective config (stored
  override, else YAML; a new DB-only niche checks every entry); an `/auto_actions/i` not in `actions` that this PUT added
  or whose action it removed; weakening the shipped YAML's safety floor (a DB-only niche has none):
  `expert_review.always: true` must stay true (`/expert_review/always`); non-empty `expert_review.when_topics` needs
  `always: true` or a non-empty `when_topics` (`/expert_review`); either of those forces `autonomy: "ask"`
  (`/autonomy`); `sensitivity: private` must stay private (`/sensitivity`) (ADR 0009 Amendment: floor covers
  when_topics). Unchanged unregistered entries round-trip (ADR 0009 Amendment 2026-10-14). Validation is
  server-side only (no dry-run route).
- `POST /v1/niches/draft {"description": "decide which job offers to apply to"}` → draft config (not saved). NOT BUILT (LATER, 8.4).
- `POST /v1/niches/reload` scope `admin`. Built: it reloads the YAML. The planned part is re-applying the DB overrides (ADR 0009).

## Sources & connectors
**PLANNED (Phase 3 step 3.5-B, not built yet).** The list, add and PATCH routes below are not live.
**Built today:** no `/v1/sources` route. The routes below are planned or not built, as marked.

- **PLANNED (Phase 3 step 3.5-B, not built yet): `GET /v1/sources`** scope `items:read` → `{"data": [{"id", "type",
  "name", "slug", "enabled", "niche_hint", "last_polled_at", "error_count", "items_today"}]}`. It never returns `config`,
  `secret_enc` or `oauth_enc`.
- **PLANNED (Phase 3 step 3.5-B, not built yet): `POST /v1/sources`** scope `admin` `{type, name, slug, config, niche_hint?}`. Phase 3 accepts
  `type ∈ {rss, google_news}` only (others → `422`). The URL is https only; `409` for a duplicate slug.
- **PLANNED (Phase 3 step 3.5-B, not built yet, ADR 0010): `PATCH /v1/sources/{id}`** scope `admin`. Body `{"enabled": true|false}` only (any
  other key → `422`). → `200` one source row (as in GET). `404` for an unknown id or another tenant's source. Idempotent.
- NOT BUILT (later phases): `POST /v1/sources` gains `gmail|instagram|webhook|telegram|…`
- NOT BUILT (later phases): `GET /v1/sources/{id}/oauth/start` → redirect (gmail, instagram); `/oauth/callback`
- NOT BUILT (later phases): `POST /v1/webhooks/{source_slug}` — inbound; header `X-DE-Signature: t=<unix>,v1=<hex hmac_sha256(secret, t + "." + body)>` (FR-91); provider-native verification for Meta (`X-Hub-Signature-256`) and Telegram (secret token header)
- `POST /v1/telegram/webhook` — Telegram Bot API updates (FR-94). Auth is the header `X-Telegram-Bot-Api-Secret-Token`, which must equal `TELEGRAM_WEBHOOK_SECRET` (403 otherwise). Only chats in `TELEGRAM_ALLOWED_CHAT_IDS` are used; others are ignored and logged. Forwarded text becomes a private `telegram` item; button presses `de:a:<id>` (approve, recommended option) and `de:r:<id>` (reject) resume the item. Always 200 for a valid update.

## Outbound webhooks (FR-42)
- `GET/POST/DELETE /v1/subscriptions` `{url, events: ["decision.ready","decision.made","action.done","item.triaged"], secret}`
- Scope `admin`. `url` must be `https` and resolve to a public address (loopback, RFC 1918, link-local, metadata,
  ULA and multicast are refused with `422`; dev-only `WEBHOOK_ALLOW_PRIVATE_URLS=true` relaxes this). `secret` is
  stored Fernet-encrypted and never returned (min 16 characters). `POST` → `201`, `DELETE` → `204`, `GET` → `{"data": [...]}`.
- Delivery: `POST url` body `{"event":"decision.made","id":"evt_<uuid7>","created_at":"…","data":{<DecisionItem>}}`
  (`data` never contains `raw`, `hints` or `callback_url`). Headers: `X-DE-Signature: t=<unix>,v1=<hex
  hmac_sha256(secret, t + "." + body)>` (same scheme as inbound, 5-min tolerance), `X-DE-Event: <event>`,
  `X-DE-Delivery: <delivery id>`. Timeout `WEBHOOK_TIMEOUT_SECONDS` (10); redirects are not followed; only `2xx` counts.
- Retries: attempt 1 at once, then 1 m, 5 m, 30 m, 2 h after each failure (5 attempts in total), then `failed`
  (dead-letter, visible in UI). A retry re-signs the same stored body with a fresh `t`. Receivers dedupe on the
  envelope `id`.
- Mechanics: emitters enqueue `jobs(kind=webhook, payload {"op":"fanout","event","event_id","extra"})` in their own
  transaction. The fan-out job writes one `webhook_deliveries` row per matching subscription and enqueues a
  `deliver` job for each. Delivery failures are recorded on the row and rescheduled by the handler, not by the queue's
  generic backoff. `data` is the item as of fan-out time.
- Per-item `callback_url`: stored only, not delivered in Phase 1 (ADR 0004).

## Feedback & learning
- `GET /v1/feedback/export?niche=news_radar&format=laya_train|laya_eval&since=…` → JSONL stream (FR-80)
- `GET /v1/feedback/shadow-report?niche=…&days=14` → per-cutoff table (FR-81). NOT BUILT yet (only `/export` exists).

## Stats
- **PLANNED (Phase 3 step 3.5-B3, not built yet): `GET /v1/stats/today`** → counts by status/niche, LLM budget used per
  provider, Laya mode and health

## Health
- `GET /health` (no auth, liveness) · `GET /health/deep` (auth) → `{db, redis, laya, llm:{gemini:…}, queue_depth, oldest_job_age_s}`

## Versioning
Breaking changes → `/v2`. Additive fields allowed in v1; clients must ignore unknown fields.
