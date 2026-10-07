# 0002 — Rate-limit store when Redis is absent

**Status:** accepted · 2026-10-07 · Requirements: FR-07, NFR-05 · Plan: phase 0 step 0.5a

## Context
FR-07 requires a per-API-key limit (default 120 req/min) answered with `429` + `Retry-After`. With Redis
configured, `RedisRateLimiter` uses a fixed window (`INCR` + `EXPIRE`, 2 commands per request). Redis is
optional (CLAUDE.md), so `app/security/rate_limit.py` needs a fallback. DATA_MODEL.md has no rate-limit table.

Free-tier facts (checked 2026-10-07):
- Neon Free: 100 CU-hours per project per month; compute suspends after 5 min idle, and suspended time
  costs nothing ([Neon pricing overview, jetadmin, 2026-09-26](https://www.jetadmin.io/blog/neon-pricing/)).
  An always-on 0.25 CU compute would use about 180 CU-hours a month, so extra per-request queries matter.
- Upstash Free: 500K commands per month ([Upstash blog, 2026](https://upstash.com/blog/upstash-vs-redis-cloud-a-2026-comparison)),
  which is why Redis is optional and its command count is kept low.
- MVP runs one API process (Compose on one VM, or one Render instance).

## Options considered
| | (a) In-process fixed window `MemoryRateLimiter` | (b) Postgres `rate_limits` table |
|---|---|---|
| Correctness | Exact for 1 process; limit × N with N processes/replicas | Exact across replicas |
| Free-tier cost | Zero; no DB or Redis traffic | One upsert per request (`INSERT … ON CONFLICT DO UPDATE`): more writes, WAL and Neon CU time |
| Latency | Microseconds | One extra DB round trip (Neon over network: milliseconds) |
| Ops burden | None; state lost on restart (window resets, acceptable) | New table + Alembic migration, row contention on hot keys, cleanup job for old windows |
| Failure mode | Cannot fail on its own | DB slowness adds latency to every request |

## Decision
**(a) `MemoryRateLimiter`**: an in-process fixed window (dict keyed by `(key, window_start)`, guarded by an
`asyncio.Lock`, expired windows pruned on access), behind the same `RateLimiter` Protocol as `RedisRateLimiter`.
Selection: `REDIS_URL` set → Redis; otherwise memory. If Redis errors at runtime, use the memory limiter for
that request (never a 500). DATA_MODEL.md is unchanged; no migration.

## Consequences
- With N API processes (uvicorn workers or replicas) and no Redis, the effective limit is **N × limit**.
  Fine at MVP (N = 1). Deploy docs must state that more than one API process requires `REDIS_URL`.
- Counters reset on restart, which briefly allows up to 2 × limit. Acceptable for a per-minute window.
- The 5,000 items/day cap in FR-07 is out of scope here: a one-minute in-memory window is not a durable
  daily counter. Whoever builds it should count persisted rows, not use this limiter.
- No extra Neon compute or Upstash commands in the Redis-less setup.

## Revisit when
- More than one API process is deployed without Redis, or
- **Phase 8 step 8.5 (multi-tenant hardening)**: untrusted tenants turn the N × limit gap into a security
  issue. Then make Redis required for multi-process deploys, or write a new ADR adopting (b).

## Migration steps
None now. To move to (b) later: add `rate_limits(key, window_start, count, PK(key, window_start))` through
Alembic, add `PostgresRateLimiter` behind the same Protocol and a cleanup job. Callers do not change.
