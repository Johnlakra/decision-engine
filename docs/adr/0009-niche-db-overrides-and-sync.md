# 0009 — Niche DB overrides: write rules and how every process sees them

**Status:** accepted · 2026-10-14 · Requirements: FR-70, FR-71, FR-72, FR-110, NFR-04 · Plan: phase 3 D3, steps 3.5-B1, 3.5b

## Context
- `NicheRegistry` (`app/niches/registry.py`) is a **process-global** in-memory map, loaded from `niches/*.yaml` at boot
  and on `POST /v1/niches/reload`. `reload(overrides=...)` is reserved and unused. Invalid files keep their previous
  version, and a missing `generic` refuses boot.
- Table `niches` (tenant_id, name unique per tenant, `config` JSONB, `version` int default 1, `enabled`, `source`,
  `updated_at` with `onupdate=now()`) exists. It has no rows yet.
- Readers of the registry run in **two kinds of process**: the API (`/v1/decide`, `POST /v1/items/{id}/decision`
  resumes the graph inline, `/v1/niches`, health) and the worker (`prepare_batch` → triage, `route`, the niche
  subgraph). `PUT /v1/niches/{name}` runs in one API process only. The API may also run more than one process.
- The worker already holds a `LISTEN jobs_new` connection, but it falls back to polling when LISTEN is unavailable.
- Facts checked 2026-10-14:
  - PostgreSQL 16 `NOTIFY` delivers only on commit, and only to sessions that are **already** listening. Nothing says
    a session that starts listening later receives earlier events ([docs](https://www.postgresql.org/docs/16/sql-notify.html)).
  - Neon Free: 100 CU-hours/project/month. Compute "suspends after 5 min, cannot be turned off" on Free
    ([neon.com/pricing](https://neon.com/pricing), fetched 2026-10-14).
- Invariants a browser-editable niche could break: "approval before irreversible actions" (autonomy `auto` +
  `auto_actions`), "agriculture safety" (expert review, `ask`), "niches are config" (no code per niche), and
  `graph/builder.reject_custom_steps` raises at graph build when any niche declares `steps`.

## Options considered (worker/API freshness)
| | (a) Fingerprint check per unit of work | (b) `LISTEN niches_changed` + `NOTIFY` on PUT | (c) Periodic reload (every N s) | (d) Redis pub/sub |
|---|---|---|---|---|
| Correctness | Always fresh at the start of each batch/request, even after a restart or a missed message | A missed notify (listener reconnecting, LISTEN unavailable, a second API process) leaves a stale registry until restart. Needs (a) or (c) as a backstop anyway | Stale for up to N s. An approval inside that window can use the old autonomy | Same miss problem. Redis is optional in this stack |
| Free-tier cost | One indexed aggregate query **only when there is work**. Zero queries while idle, so Neon can still scale to zero | Zero queries, but a held connection | A query every N s keeps Neon awake (5-min suspend never triggers) and burns CU-hours | Upstash command budget |
| Ops burden | One helper, no new channel | A second channel, reconnect handling | Trivial | New dependency on the critical path |

## Decision
### 1. Freshness: (a) fingerprint check
`app/niches/overrides.py` (owned by backend-builder, 3.5-B1):
```python
async def overrides_fingerprint(session) -> tuple[int, int, datetime | None]
    # SELECT count(*), coalesce(sum(version), 0), max(updated_at) FROM niches
async def load_overrides(session) -> dict[str, dict]          # name -> config, for the single tenant
async def sync_registry(session, registry=None) -> bool        # reload if the fingerprint changed; True if reloaded
```
- `sync_registry` keeps the last fingerprint in the registry object. When it changes, it calls
  `registry.reload(overrides=await load_overrides(session))` (in a thread, like `/reload`). The reload stays
  all-or-nothing per niche.
- **Call sites** (every unit of work that reads the registry): `Worker.run_once` after a **non-empty** claim and before
  `prepare` (one call per batch, not per job). In the API, `/v1/decide`, `POST /v1/items/{id}/decision`, and
  `GET /v1/niches[/{name}]`. `PUT /v1/niches/{name}` reloads directly after commit. `POST /v1/niches/reload` passes the
  current overrides too, so reloading YAML never drops DB overrides.
- `sync_registry` failure (DB error): log, then keep serving the current registry. Never raise into the pipeline (the
  item is not lost, and the job retries on its own error path if the DB is really down).

### 2. Override semantics
- A DB row's `config` is a **complete** niche config that **replaces** the YAML niche of the same name (no deep merge).
  A row with no YAML file of that name is a DB-only niche (allowed, for the FR-72 wizard later).
- Single tenant (FR-110): `load_overrides` reads all rows. If rows belong to more than one `tenant_id`, it logs an
  error and applies **none** (fail closed to YAML) until Phase 8.5 makes the registry per-tenant.
- At reload, an override that fails validation (for example after a schema change) is skipped: the YAML version (or the
  previous good version) stays, and the error appears in `registry.errors` and `/health/deep`. `generic` is always
  present.
- `niches.enabled` mirrors `config.enabled` (written together). `source = "db"`. The registry reads `config` only.

### 3. `PUT /v1/niches/{name}` write rules (scope `admin`)
Body = one niche config as a JSON **object** (the client converts YAML to JSON). Server steps, all before any write:
1. JSON Schema (`schemas/niche.schema.json`) via the loader's validator → all errors (see ADR 0011).
2. Semantic checks, each a `{json_pointer, message}` error:
   - `/name` must equal the path `name`.
   - `generic`: `/enabled` must be `true`.
   - `/steps` must be absent or empty ("custom steps need a new ADR").
   - every `/actions/i` is a registered action (`actions.registry.registered()`), and every `/tools/i` a registered
     tool (`tools.registry.registered()`). **Amended 2026-10-14:** only for entries this PUT adds (see Amendment).
   - every `/auto_actions/i` is also in `actions`. **Amended 2026-10-14:** only for changed entries (see Amendment).
   - **Safety floor from the YAML:** when the YAML version of this niche has `expert_review.always: true`, the override
     must keep `expert_review.always: true` and `autonomy: "ask"`. When the YAML version is `sensitivity: private`, the
     override must stay `private`. (No niche name in code: the floor comes from the shipped YAML.)
     **Amended 2026-10-14:** the floor also covers `expert_review.when_topics` (see Amendment: floor covers
     when_topics).
3. Upsert the row in one transaction: `config.version` is set by the server to the new row `version` (the body's
   `version` is ignored), and `version = version + 1` on update (1 on insert). Then commit and `sync_registry`.

Responses: `200` with the effective niche (same shape as `GET /v1/niches/{name}`). `422` problem+json
`title: "Niche validation failed"`, `errors[{json_pointer, message}]`, with nothing written. `404` is never returned
for an unknown name, because PUT may create a DB-only niche, which must pass the schema.

### 4. Read shapes
- `GET /v1/niches` (items:read) → `{data: [{name, label, description, enabled, autonomy, auto_actions,
  source: "yaml"|"db", version, laya_mode}]}` (`laya_mode` per ADR 0008).
- `GET /v1/niches/{name}` (items:read) → `{name, source, version, config: {...effective...}, yaml: "<text>"}`. `yaml`
  is the file text when `source = "yaml"`, otherwise `yaml.safe_dump(config, sort_keys=False, allow_unicode=True)`
  (comments are not kept for DB overrides). `404` problem+json for an unknown name.

## Consequences
- No migration: the table and `version` exist. No new env var, channel or dependency. No paid service.
- Each worker batch and each niche-reading request costs one extra small query. Idle processes cost nothing, so Neon
  can still scale to zero.
- Any API process count is safe, with no sticky routing needed.
- A browser user with `admin` (all allow-listed users, plan D9) can change autonomy, but cannot weaken the YAML
  safety floor, cannot declare custom steps, and cannot add unregistered actions or tools (entries already in the
  effective config may stay, see Amendment). Irreversible actions still need
  `autonomy: auto` **and** the allow-list (the CLAUDE.md rule).
- There is no "revert to YAML" (row delete) in Phase 3. The fingerprint already handles deletes, so adding
  `DELETE /v1/niches/{name}` later is cheap.

## Amendment — 2026-10-14: registry checks apply to changed entries only (owner decision, option A)
**Reason.** The shipped niches reference actions and tools that are not built yet: `inbox` lists `draft_reply`,
`news_radar` and `agriculture` list `notify`, and `agriculture` lists four tools that are not registered. Under the
original rule, a `GET` → edit autonomy → `PUT` round trip of any of these niches fails with `422`, even though the edit
did not touch those entries. Registering placeholder actions or tools to make the check pass was rejected: a
placeholder would look like working behavior in the UI and in decisions.

**Rule (replaces the two registry bullets in Decision §3, step 2).** "Baseline" = the currently effective config of
this niche: the stored DB override if a row exists, otherwise the shipped YAML. A DB-only niche created by this PUT has
an empty baseline, so every entry counts as added. Entries compare by string value; order does not matter.
- `/actions/i`: refused with `422` only when the value is **not in the baseline's `actions`** and is not registered.
- `/tools/i`: refused with `422` only when the value is **not in the baseline's `tools`** and is not registered.
- `/auto_actions/i`: refused with `422` when the value is not in the body's `actions` **and** either the value is not
  in the baseline's `auto_actions` or it was in the baseline's `actions` (that is, this PUT added the auto entry or
  removed its action). An auto entry that is unchanged and was already outside `actions` may round-trip.
- Removing entries is always allowed. The error `json_pointer` points at the body index (for example `/actions/2`).

**Unchanged.** `/name` = path, `generic` stays enabled, `/steps` absent or empty, the YAML safety floor
(`expert_review.always` + `autonomy: "ask"`, `sensitivity: private`), single tenant (rows from more than one tenant →
none applied), the schema check (ADR 0011), and versioning.

**Runtime behavior.** An unchanged entry that names an unregistered action or tool behaves at load and run time
exactly as it does today for the YAML: the niche loads, the tool runner skips names it does not know, and the decide
node drops actions not in `niche.actions ∩ actions.registered()` (logged, see `docs/plans/phase-1.md`). So an
unregistered action can never run, and "approval before irreversible actions" still holds. A **newly added**
unregistered action or tool is refused with `422`, and nothing is written.

**Migration for this amendment.** backend-builder (3.5-B1): the PUT validator takes the baseline config. Tests in
`tests/integration/test_niches_api.py`: (1) PUT of the shipped `agriculture`, `inbox` and `news_radar` configs with
only `autonomy` or `description` changed → `200`; (2) adding an unregistered action or tool → `422` at that index;
(3) a DB-only niche with an unregistered action → `422`; (4) adding an `auto_actions` entry not in `actions`, or
removing an action that an existing auto entry names → `422`; (5) the baseline is the stored override when one exists.

## Amendment — 2026-10-14: floor covers when_topics
**Reason.** The original floor only looked at `expert_review.always`. A shipped niche such as `agriculture` asks for
expert review through `expert_review.when_topics` instead, so under the original text an admin could clear the topics
and set `autonomy: auto`, which would break the agriculture-safety invariant in CLAUDE.md ("always `ask` autonomy
with an expert-review flag"). The code in `apps/api/app/niches/rules.py` (`_floor`) already enforces the stricter rule
below; this amendment makes the ADR match it.

**Rule (replaces the safety-floor bullet in Decision §3, step 2).** "Shipped" = the YAML version of this niche
(`registry.yaml_config(name)`), not the stored DB override. A DB-only niche (no YAML file) has no floor. Each check is
a separate `422` error:
| Shipped YAML has | Override must have | Error `json_pointer` · message |
|---|---|---|
| `expert_review.always: true` | `expert_review.always: true` | `/expert_review/always` · "expert review is required by the shipped niche" |
| non-empty `expert_review.when_topics` | `expert_review.always: true` **or** a non-empty `expert_review.when_topics` | `/expert_review` · "expert review topics of the shipped niche cannot be removed" |
| `expert_review.always: true` **or** non-empty `expert_review.when_topics` | `autonomy: "ask"` | `/autonomy` · "autonomy must stay 'ask' (shipped niche needs expert review)" |
| `sensitivity: private` | `sensitivity: private` | `/sensitivity` · "this niche must stay private" |

- The override's topic list does not have to equal the shipped list: it may change or narrow it, as long as it stays
  non-empty (or `always` is turned on). Making the floor stricter (for example `always: true` on a niche that ships
  with topics only) is always allowed.
- A public shipped niche may become `private`; a niche with no expert review in YAML has no autonomy floor.

**Example.** Shipped `agriculture` (`autonomy: ask`, non-empty `when_topics`): a PUT with
`expert_review: {always: false, when_topics: []}` → `422` with `/expert_review`; a PUT with `autonomy: "auto"` →
`422` with `/autonomy`; the unchanged effective config → `200`.

**Consequences.** No schema, API shape or migration change: the `422` problem+json shape is the same. Topic matching
at run time is unchanged (this rule governs only what an override may save).

**Migration for this amendment.** None for code: `_floor` already implements it. Tests already in
`apps/api/tests/integration/test_niches_api.py`: `test_safety_floor_agriculture_refuses_auto_autonomy`,
`test_safety_floor_agriculture_ask_with_topics_succeeds`, `test_safety_floor_agriculture_refuses_removing_topics`,
`test_safety_floor_private_stays_private`.

## Revisit when
- An action or tool named by a shipped niche gets registered: nothing to change. If one is retired, remove it from the
  YAML in the same commit.
- Multi-tenant (Phase 8.5): the registry becomes per-tenant (key the cache by tenant_id, same fingerprint per tenant).
- The FR-72 wizard writes DB-only niches.
- Profiling shows the fingerprint query matters (then add LISTEN as an optimization, keeping (a) as the backstop).

## Migration steps
1. backend-builder (3.5-B1): `niches/overrides.py`, `registry.reload(overrides=...)` merge + fingerprint attribute,
   routes, `Worker.run_once` call site, call sites in `decide.py` and `items.py` decision route. Tests:
   `tests/unit/test_niche_overrides.py` (merge, invalid override keeps YAML, multi-tenant rows → none applied,
   fingerprint change triggers exactly one reload, DB error keeps the registry) and
   `tests/integration/test_niches_api.py` (every 422 rule above, version bump, generic disable refused, a
   second registry instance sees the PUT after `sync_registry`).
2. architect: API.md Niches section (done with this ADR).
3. backend-builder (3.5-B5): `make sdk`.
4. Rollback: delete the `niches` rows. The next `sync_registry` falls back to YAML.
