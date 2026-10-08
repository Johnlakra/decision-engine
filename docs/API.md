# HTTP API (v1)

Base: `https://<host>/v1`. JSON in and out (UTF-8). OpenAPI at `/openapi.json`, docs at `/docs`.
Auth: `Authorization: Bearer de_<prefix>_<secret>` (API key, scoped). Errors: RFC 9457
`application/problem+json` `{type, title, status, detail, errors?}`.
Pagination: cursor (`?cursor=<opaque>&limit=50`, max 200) → `{data: [...], next_cursor}`.

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
`{"items": [ <item>, … ≤500 ]}` → `207 {"results": [{"index":0,"id":"…","status":"new"}, {"index":1,"error":{…}}]}`

### `GET /v1/items?status=awaiting_approval&niche=inbox&source=gmail&q=text&cursor=…`
### `GET /v1/items/{id}` → full DecisionItem (schemas/decision_item.schema.json)
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
### `POST /v1/items/{id}/undo` — within 10 s of a decision (FR-53)
### `POST /v1/items/{id}/retry` — failed items
### `POST /v1/items/{id}/retriage` — rerun normalise+triage (after a niche change)

## Synchronous decisions
### `POST /v1/decide` — scope `decide` (FR-35)
```json
{
  "state": "text or JSON object to decide about",
  "questions": {                                         // Laya format (docs/LAYA.md)
    "sell": {"type": "choice", "instructions": "Sell the wheat now or hold?",
             "criteria": {"A": "sell now", "B": "hold 1-2 weeks", "C": "hold > 2 weeks"}}
  },
  "niche": "agriculture",          // optional: also run that niche's tools + LLM decision
  "explain": true,                 // optional: LLM rationale
  "language": "pa",                // optional: answer language for rationale
  "sensitivity": "public"          // optional, default public (ADR 0005); private → only private_ok providers
}
```
→ `200 {"answers": {"sell": {"choice":"B","probabilities":{…},"confidence":0.71}}, "decision": {…}?, "explanation": "…"?, "model": "laya-english", "fallback": false}`
- `fallback: true` when Laya gave no opinion and the LLM fallback classifier answered. Laya mode does not gate this endpoint.
- `decision` only with `niche` (runs extract/tools/decide/policy; writes nothing). `explanation` (additive) only with
  `explain` and no `niche`.
- Errors: `422` invalid questions (schema, ≤ 16 questions) · `503` fallback needed but unavailable, or private with no
  `private_ok` provider (`type: .../no-private-provider`) · `504` after `DECIDE_TIMEOUT_SECONDS` (default 30).

## Uploads (FR-04)
`POST /v1/uploads` multipart `file` + `mapping` JSON:
```json
{"source": "csv", "source_ref_column": "id", "title": "subject", "body": "message",
 "sender": "from", "received_at": "date", "niche_hint": "inbox", "sensitivity": "private"}
```
→ `202 {"upload_id": "…"}` · `GET /v1/uploads/{id}` → `{status, total, done, failed, errors:[…≤50]}`

## Niches (FR-70, FR-72)
- `GET /v1/niches` · `GET /v1/niches/{name}` (effective config: YAML + DB override)
- `PUT /v1/niches/{name}` scope `admin` — body = niche config; validated against schemas/niche.schema.json
- `POST /v1/niches/draft {"description": "decide which job offers to apply to"}` → draft config (not saved)
- `POST /v1/niches/reload` scope `admin`

## Sources & connectors
- `GET/POST /v1/sources` `{type: "rss"|"gmail"|"instagram"|"webhook"|"telegram"|…, name, config, niche_hint?, enabled}`
- `GET /v1/sources/{id}/oauth/start` → redirect (gmail, instagram); `/oauth/callback`
- `POST /v1/webhooks/{source_slug}` — inbound; header `X-DE-Signature: t=<unix>,v1=<hex hmac_sha256(secret, t + "." + body)>` (FR-91); provider-native verification for Meta (`X-Hub-Signature-256`) and Telegram (secret token header)

## Outbound webhooks (FR-42)
- `GET/POST/DELETE /v1/subscriptions` `{url, events: ["decision.ready","decision.made","action.done","item.triaged"], secret}`
- Scope `admin`. `url` must be `https` and resolve to a public address (loopback, RFC 1918, link-local, metadata,
  ULA and multicast are refused with `422`; dev-only `WEBHOOK_ALLOW_PRIVATE_URLS=true` relaxes this). `secret` is
  stored Fernet-encrypted and never returned.
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
- `GET /v1/feedback/shadow-report?niche=…&days=14` → per-cutoff table (FR-81)

## Stats
- `GET /v1/stats/today` → counts by status/niche, LLM budget used per provider, Laya mode and health

## Health
- `GET /health` (no auth, liveness) · `GET /health/deep` (auth) → `{db, redis, laya, llm:{gemini:…}, queue_depth, oldest_job_age_s}`

## Versioning
Breaking changes → `/v2`. Additive fields allowed in v1; clients must ignore unknown fields.
