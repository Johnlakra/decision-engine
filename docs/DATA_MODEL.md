# Data model (Postgres 16 + pgvector)

All tables: `id uuid` (UUIDv7) primary key, `tenant_id uuid not null` (except `tenants`),
`created_at timestamptz default now()`, `updated_at timestamptz`. Index every `(tenant_id, …)` query path.
JSON columns are `jsonb`. Enums are `text` + CHECK (easier migrations than PG enums).

| Table | Key columns | Notes |
|---|---|---|
| `tenants` | name, timezone (`Asia/Kolkata`), plan | one row at MVP |
| `tenant_settings` | tenant_id PK, settings jsonb | laya_mode, autonomy overrides, digest_hour, quiet_hours, interests, languages |
| `users` | email unique, name, role (`owner`/`member`/`expert`) | web login allow-list mirror |
| `api_keys` | prefix unique, hash, scopes text[], name, last_used_at, revoked_at | secret shown once |
| `sources` | type, name, slug unique per tenant, config jsonb, secret_enc, oauth_enc, niche_hint, sensitivity, enabled, cursor jsonb, last_polled_at, error_count | tokens Fernet-encrypted |
| `items` | source, source_ref, received_at, status, raw jsonb, content jsonb, language, sensitivity, niche, triage jsonb, decision jsonb, risk, urgency smallint, deadline_at, related_to uuid, embedding vector(768) null, laya_mode, error text, attempts | UNIQUE(tenant_id, source, source_ref); idx (tenant_id, status, urgency desc, deadline_at); ivfflat/hnsw on embedding |
| `jobs` | kind (`process`,`action`,`webhook`,`poll`,`upload`,`digest`), item_id null, payload jsonb, status (`queued`,`running`,`done`,`failed`), run_at, attempts, max_attempts (5), locked_by, locked_at, last_error | partial idx on (run_at) where status='queued'; claim via `FOR UPDATE SKIP LOCKED` |
| `niches` | name, config jsonb, version int, enabled, source (`yaml`/`db`) | DB rows override YAML of the same name |
| `decisions` | item_id, verdict, option, edits jsonb, decided_by (`human`/`auto`/`llm`), user_id, latency_ms, undone_at | append-only |
| `feedback` | item_id, niche, kind (`decision`,`triage_correction`,`vote`), state_text, questions jsonb, gold jsonb, label_source (`human`/`llm`), used_for_training bool | the Laya training set |
| `actions_log` | item_id, action, params jsonb, idem_key unique, status, result jsonb, reversible, undone_at | |
| `llm_usage` | provider, model, purpose, item_id, prompt_tokens, completion_tokens, cost_inr numeric, latency_ms, ok, error_code | daily budgets fall back to counting here when Redis is absent |
| `webhook_subscriptions` | url, events text[], secret_enc, enabled | |
| `webhook_deliveries` | subscription_id, event, payload jsonb, status, attempts, next_attempt_at, last_status_code | |
| `uploads` | filename, mapping jsonb, status, total, done, failed, errors jsonb | |
| `tool_cache` | tool, args_hash, result jsonb, expires_at | Agmarknet/weather caching |
| `farmers` (phase 7) | phone_hash, language, village, district, crops jsonb, land_acres, consent_at | minimal PII, consent required |
| `advisories` (phase 7) | farmer_id, item_id, inputs jsonb, output jsonb, needs_expert, reviewed_by, reviewed_at | |
| LangGraph tables | created by `AsyncPostgresSaver.setup()` | do not edit by hand |

## `items.triage` jsonb
```json
{
  "mode": "on", "model": "laya-english", "laya_version": "0.3.27", "fallback": false,
  "answers": {
    "needs_decision": {"choice": "A", "probabilities": {"A": 0.91, "B": 0.09}, "confidence": 0.84},
    "niche": {"choice": "inbox", "probabilities": {…}, "confidence": 0.77},
    "urgency": {"score": 1.6, "level": 2, "confidence": 0.62},
    "risk": {"choice": "normal", "probabilities": {…}, "confidence": 0.93},
    "keep": {…}
  },
  "decided_by": "laya",   // laya | llm_fallback | human
  "latency_ms": 41
}
```

## `items.decision` jsonb (= DecisionOut)
```json
{
  "options": [{"id": "A", "label": "Reply today accepting the meeting", "actions": [{"type": "draft_reply", "params": {"tone": "warm"}}]},
              {"id": "B", "label": "Ask to move to next week", "actions": [{"type": "draft_reply", "params": {…}}]}],
  "recommended": "A",
  "rationale": "The sender is your client and the date is tomorrow; you are free in your calendar.",
  "evidence": [{"kind": "field", "ref": "content.entities.date"}, {"kind": "tool", "ref": "calendar.free", "as_of": "2026-10-07"}],
  "deadline": "2026-10-08T04:30:00Z",
  "confidence": 0.74,
  "autonomy": "ask",
  "model": "gemini-flash-lite-latest"
}
```

## Retention
`raw` and `content.body` of `private` items purged after `RAW_RETENTION_DAYS` (default 180); decisions and
feedback keep `state_text` truncated to 700 chars for training unless the tenant opts out.
