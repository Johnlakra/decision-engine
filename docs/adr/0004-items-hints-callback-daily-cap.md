# 0004 — Migration 0002: `items.hints`, `items.callback_url`, daily item cap per tenant

**Status:** accepted · 2026-10-08 · Requirements: FR-01, FR-06, FR-07, FR-11, NFR-01, NFR-04, NFR-06 ·
Plan: phase 1 steps A1, 1.1 (owner question Q3)

## Context
- `POST /v1/items` (API.md, `schemas/ingest_item.schema.json`) accepts optional `hints` and `callback_url`. The
  Phase 0 `items` table (migration `0001`) has no column for either. FR-06 says `items.raw` stores the **untouched**
  payload, and the normaliser (FR-11, C6) needs the hints separately ("hint > LLM > heuristic").
- FR-07 asks for a 5,000 items/day cap "per API key". `items` has no `api_key_id`, and ADR 0002 explicitly left the
  daily cap to "count persisted rows". Counting today's rows needs an index: the only `items` indexes are the
  unique `(tenant_id, source, source_ref)`, `ix_items_queue (tenant_id, status, urgency desc, deadline_at)` and the
  embedding HNSW index.
- **Owner answer Q3 (2026-10-08):** `callback_url` is stored only in Phase 1. Delivery happens in Phase 2. Tenant
  subscriptions (FR-42) cover the Phase 1 acceptance check.
- NFR-01: `POST /v1/items` p95 < 300 ms, so the cap check must be one indexed query.

## Options considered

### Where hints and callback_url live
| | (a) New nullable columns `hints jsonb`, `callback_url text` | (b) Wrap `raw` as `{payload, hints, callback_url}` | (c) Put hints into `content` before normalising |
|---|---|---|---|
| FR-06 | `raw` is byte-for-byte the payload | Bent: `raw` is no longer the payload; every reader must unwrap | `raw` intact, but `content` would mean "maybe normalised" |
| Migration | One reversible Alembic revision (metadata-only `ADD COLUMN`, no rewrite in PG 16) | None | None |
| Re-normalise | Re-run reads `raw` + `hints` directly | Unwrap first | Hints lost once `content` is overwritten |
| Privacy | `hints.body` may hold a private body: purge with `raw` (NFR-06) | Same, purged with `raw` | Purged with `content.body` |
| Free-tier cost | None measurable | None | None |

### How the daily cap is counted
| | (a) Per tenant: `count(*)` of today's rows on `(tenant_id, created_at)` | (b) Per API key: add `items.api_key_id` + index | (c) Counter in Redis / a counter table |
|---|---|---|---|
| Accuracy | Exact persisted count (soft: concurrent requests can overshoot slightly) | Exact per key | Exact if Redis is up; drifts on Redis loss |
| Cost | One index-range count per request, no writes | Extra column + index, and the key is an auth detail leaking into the item model | Upstash commands per item (500K/month budget), or a hot-row update on Neon |
| Ops burden | Index only | Column, index, backfill rule for connector-created items (no key) | Second source of truth, reset job |
| Meaning | Protects the tenant's free-tier LLM budget, which is per tenant anyway | Per-key fairness, which matters only with many keys | Same as (a) |

## Decision
1. **Columns (option a).** Alembic revision `0002` (`down_revision = "0001"`, file
   `apps/api/alembic/versions/0002_item_hints.py`):
   - `items.hints jsonb NULL`: the validated `Hints` model dumped with `exclude_none=True`. `NULL` when the request had
     no hints.
   - `items.callback_url text NULL`: syntax-checked only at ingest (absolute `https` URL, ≤ 2,000 chars; `http` only when
     `WEBHOOK_ALLOW_PRIVATE_URLS=true`). No DNS lookup at ingest (NFR-01). `check_url` (SSRF) runs at **delivery time**
     when delivery ships in Phase 2. Phase 1 never sends to it.
   - Index `ix_items_tenant_created ON items (tenant_id, created_at)`.
   - `downgrade()` drops the index, then both columns. Downgrade loses stored hints and callback URLs (the payload in
     `raw` is unaffected). It is reversible schema-wise (P6).
   - `raw` stays exactly the request `payload` (FR-06). `items.sensitivity` stays the resolved value (ADR 0005 decides the
     defaults). `hints.sensitivity` is kept in `hints` as the caller's request.
2. **Never public.** `hints` and `callback_url` are never returned by `GET /v1/items*` or in webhook payloads
   (`DecisionItemOut`, `schemas/decision_item.schema.json`). They are never logged (log ids only).
3. **Retention.** `hints` follows `raw`: for `private` items it is purged after `RAW_RETENTION_DAYS` (DATA_MODEL.md).
4. **Daily cap (option a), FR-07 amended.** The 5,000 items/day cap (`ITEMS_PER_DAY`, default 5000) is **per tenant**,
   counted as `SELECT count(*) FROM items WHERE tenant_id = :t AND created_at >= <today 00:00 UTC>` (server
   `created_at`, never the client's `received_at`). The day is the **UTC** day, matching the LLM budget reset
   (LLM_GATEWAY.md).
   - The check runs once per request, before inserting. If the count is already ≥ the cap: `429` problem+json
     (`type: .../daily-item-cap`, `title: "Daily item cap reached"`) with `Retry-After` = whole seconds until the next
     00:00 UTC (minimum 1).
   - Below the cap, the whole request is accepted, so a bulk call can overshoot by up to 499 rows, and concurrent
     requests can overshoot slightly. This is a **soft cap** that protects free-tier budgets. It is not a billing
     meter.
   - Idempotent repeats (`200`, no new row) do not count. Rows created by connectors and uploads count, since they are
     tenant items too.
   - The per-key 120 req/min limit (ADR 0002) is unchanged and still per key.

## Consequences
- `items` gains two nullable columns and one btree index. The write cost per insert is negligible at 5,000/day.
- The (tenant_id, created_at) index also serves future "today" stats (`GET /v1/stats/today`).
- `GET /v1/items` keeps the UUIDv7 `id` cursor (plan 1.1). Because UUIDv7 is time-ordered, `id` order ≈ `created_at`
  order. If listing gets slow, a `(tenant_id, id DESC)` index is the follow-up, not a new cursor format.
- A tenant with several API keys shares one daily allowance. FR-07's text is updated to say so.
- Phase 2 must add `callback_url` delivery (SSRF check at send time, the same signing as subscriptions) before any
  documentation promises it. Until then API.md marks it "stored, not yet delivered".

## Revisit when
- Phase 8.5 (multi-tenant hardening) needs per-key quotas, or paying plans need exact metering (then a counter table
  with a new ADR).
- `callback_url` delivery ships (Phase 2): record the delivery and retry rules in API.md.

## Migration steps
1. backend-builder (A1): `app/models/item.py` adds `hints: Mapped[dict | None]` (JSONB) and
   `callback_url: Mapped[str | None]` (Text) and the index in `__table_args__`. Write `0002_item_hints.py` by hand
   (reviewed autogenerate is fine, but it must not touch `checkpoint*` tables, see ADR 0003).
   Test `tests/integration/test_migration_0002.py`: upgrade → downgrade to `0001` → upgrade.
2. backend-builder (A1): `core/config.py` `items_per_day: int = 5000` and `.env.example` `ITEMS_PER_DAY=5000`.
3. backend-builder (1.1): `ingest_one` writes the columns; the cap check sits in the router before the service call.
4. Rollback: `alembic downgrade 0001`.
