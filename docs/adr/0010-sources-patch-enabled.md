# 0010 — `PATCH /v1/sources/{id}` changes `enabled` only

**Status:** accepted · 2026-10-14 · Requirements: FR-90, FR-60, NFR-04, NFR-07 · Plan: phase 3 D4, steps 3.5-B2, 3.5a, 3.5c

## Context
- API.md lists `GET/POST /v1/sources` only. The Sources screen (3.5c) wants an enable switch per source.
- `sources.enabled` exists (default `true`). The scheduler (`connectors/schedule.py`) only enqueues enabled sources,
  and `connectors/poll.handle_poll` drops a queued poll for a disabled source, so a switch takes effect on the next tick
  with no other code.
- `scripts/load_feeds.py` → `connectors/catalog.upsert_feed` sets `enabled = True` on **existing** rows each time it
  runs, so it would silently undo a user's switch.
- There is no `DELETE` in Phase 3. A noisy or broken feed spends the free-tier budgets (FR-60s: normalise/triage
  LLM calls) until it can be stopped.

## Options considered
| | (a) `PATCH` with `{enabled}` only | (b) `PATCH` with any editable field (name, config, niche_hint, sensitivity) | (c) Drop the switch (no write besides POST) |
|---|---|---|---|
| Value | Stop or resume a feed without losing its cursor, items or slug | Full editing | The user cannot stop a feed except with SQL |
| Risk | None. Disabling is the safe direction; enabling resumes a source that already passed validation on create | `config` edits need the same https/SSRF validation as POST, and `sensitivity` edits touch the privacy rule (a private source turned public sends DMs to free tiers) | Budgets burn on a bad feed |
| Contract / ops | One additive route, one proxy rule | Larger surface to secure and test | None |
| Free-tier cost | Reduces it (stops polling) | Same | Worst |

## Decision
**(a).** `PATCH /v1/sources/{id}`, scope `admin`.
- Path `id`: UUID. Request body `SourcePatch` with `extra="forbid"`: `{"enabled": <bool>}` (required). Any other key
  → `422` (Pydantic shape `errors[{field, message, code}]`). That includes `config`, `secret_enc`, `oauth_enc`,
  `sensitivity`, `slug`, `type`, `name`, `niche_hint`, `cursor`, `error_count` and `last_polled_at`.
- `200` → the same `SourceOut` object as one row of `GET /v1/sources` (`{id, type, name, slug, enabled, niche_hint,
  last_polled_at, error_count, items_today}`). It never includes `config`, `secret_enc` or `oauth_enc`.
- `404` problem+json for an unknown id or another tenant's source (no existence leak). The call is idempotent: the
  same value → `200`, no write.
- It writes only `enabled` (and `updated_at`). It does **not** reset `error_count` or `cursor`, and it does not enqueue
  a poll. The scheduler picks an enabled source up on its next tick.
- `upsert_feed` must keep an existing row's `enabled` value and set `enabled=True` only on insert, so the user's
  switch wins over the catalog loader.

Example:
```json
// PATCH /v1/sources/0192f0c2-7a1e-7c3b-9d1e-2f4a5b6c7d8e   {"enabled": false}
// 200
{"id":"0192f0c2-7a1e-7c3b-9d1e-2f4a5b6c7d8e","type":"rss","name":"Example feed","slug":"example-feed",
 "enabled":false,"niche_hint":"news_radar","last_polled_at":"2026-10-14T05:00:00Z","error_count":0,"items_today":4}
```

## Consequences
- An additive v1 route, so the SDK regenerates (`patch_source`). The web proxy adds `PATCH` to `ProxyMethod`/`BODY_METHODS`
  for `sources/{uuid}` only.
- Editing feed URLs or queries means creating a new source, and disabling the old one, in Phase 3.
- Future push sources (webhook, Telegram, Instagram, Phases 4–5) must also honour `enabled`: a disabled push source
  answers the provider `200` (so it does not retry storms) and ingests nothing. Their connector ADRs must say so.

## Revisit when
- Phase 4/5 connector setup needs editable config or secrets (then a wider PATCH with validation per type, or a
  dedicated reconnect flow).
- A `DELETE` (with an item-retention rule) is wanted.

## Migration steps
1. backend-builder (3.5-B2): route + `SourcePatch`/`SourceOut` in `schemas/sources.py`. Tests: toggle both ways,
   idempotent, extra key → 422, other tenant → 404, response never has `config`. Also `catalog.upsert_feed` keeps
   `enabled` on existing rows, with a unit test (a disabled row stays disabled after a re-load).
2. frontend-builder (3.5a): proxy rule. (3.5c): switch with optimistic update and rollback on error.
3. backend-builder (3.5-B5): `make sdk`. API.md is updated with this ADR.
4. Rollback: remove the route. Rows keep their `enabled` value.
