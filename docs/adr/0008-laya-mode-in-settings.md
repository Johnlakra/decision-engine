# 0008 — Laya mode editable as `off`/`shadow` through `/v1/settings`; `on` stays gated

**Status:** accepted · 2026-10-14 · Requirements: FR-23, FR-24, FR-43, FR-81 · Plan: phase 3 D2, steps 3.5-B4, 3.5b, 3.5e

## Context
- `triage/modes.resolve_mode(tenant_settings, niche, default)` already reads `tenant_settings.settings.laya_mode` and
  `laya_mode_by_niche` (per-niche override > tenant > env `LAYA_MODE` > `shadow`). Invalid values are ignored, and
  the fallback is never `on`. Nothing can write these keys today except direct SQL.
- The worker loads tenant settings from the DB for each triage batch (`triage/service._load_settings`), so a write is
  seen on the next batch. No reload is needed.
- LAYA.md §5: a niche switches to `on` only when Laya decides ≥ 50 % of items with ≤ 3 % wrong against gold and 0 wrong on
  `scam_or_phishing`, **and** the switch is recorded in `docs/adr/`. That gate cannot be checked by a form.
- `PUT /v1/settings` today: `SettingsIn` with `extra="forbid"` and five required fields. It merges into the stored JSON
  and keeps keys it does not own. The web `SettingsForm` sends exactly those five fields.
- Pydantic validation errors come out as `422` problem+json `errors[{field, message, code}]` (`core/errors.py`).

## Options considered
| | (a) Optional, nullable fields on `SettingsIn/Out`; `on` refused unless it is already stored | (b) Separate `PUT /v1/laya/mode` endpoint | (c) Keep modes env-only (no UI) |
|---|---|---|---|
| Contract change | Additive (old clients that omit the fields keep working) | New route, proxy rule, SDK op | None |
| Safety of `on` | Server-side refusal; the calibration gate stays with an ADR plus an ops change | Same | Same |
| UX | Global on Settings, per niche on the Niches cards | Same | Needs a redeploy to go back to `off` while Laya misbehaves |
| Ops / cost | 0 | One more route to secure and test | 0, but no quick kill switch |

Within (a), required fields were rejected because the existing web form and SDK callers would start getting `422`.
"Effective value in `Out`" was rejected, because a client that echoes it back would turn an env default into a stored
override, or would be refused when the env default is `on`.

## Decision
**(a).** Contract:

`SettingsIn` gains two **optional** fields. *Absent* means "leave the stored value unchanged" (the route merges with
`model_dump(exclude_unset=True)` for these two keys):

| Field | Type | Meaning |
|---|---|---|
| `laya_mode` | `"off" \| "shadow" \| "on" \| null` | Tenant mode. `null` deletes the key, so the env `LAYA_MODE` applies. |
| `laya_mode_by_niche` | `{ <niche name>: "off" \| "shadow" \| "on" }` | **Full replacement** of the map. A niche missing from the map inherits the tenant mode. `{}` clears every override. Max 50 entries. |

Rules (the route checks them after Pydantic, so all of them return `422` problem+json with `errors[{field, message, code}]`):
1. **Gate.** The value `on` is accepted only when it equals the value already stored for the same key (a no-op re-send).
   Any change *to* `on` → `422`, `type: https://decision-engine/problems/laya-mode-gated`,
   `title: "Laya 'on' needs the calibration gate"`, `code: "laya_mode_gated"`, `field: "body.laya_mode"` or
   `"body.laya_mode_by_niche.<name>"`. Changing *from* `on` to `off`/`shadow` is always allowed (that is the kill switch).
2. Map keys must match `^[a-z][a-z0-9_]{1,39}$` **and** name a niche in the registry (enabled or not). Otherwise `422`,
   `code: "unknown_niche"`.
3. The stored keys are the existing ones read by `resolve_mode`: `laya_mode` and `laya_mode_by_niche`. A tenant `null`
   removes `laya_mode` from the JSON, and it is never stored as JSON `null`.

`SettingsOut` gains three fields (always present):

| Field | Type | Source |
|---|---|---|
| `laya_mode` | `"off" \| "shadow" \| "on" \| null` | Stored tenant value. `null` = not set. Invalid stored values read as `null`. |
| `laya_mode_by_niche` | `{ name: "off" \| "shadow" \| "on" }` | Stored map. Invalid entries are dropped. |
| `laya_mode_default` | `"off" \| "shadow" \| "on"` | Read-only env `LAYA_MODE`, so the UI can show "Default (shadow)". |

`GET /v1/niches` rows also carry `laya_mode` = `resolve_mode(settings, name, env)` (read-only, effective), so the
Niches cards need no extra request. The Niches screen changes a per-niche mode by `GET /v1/settings`, then
`PUT /v1/settings` with the full form body and the edited `laya_mode_by_niche` (read-modify-write. With one owner
(FR-110) last-write-wins is accepted).

UI: the selector offers Default · Off · Shadow. `On` is shown disabled with "Needs calibration". When the stored value
is `on`, the UI shows it read-only and offers only Off/Shadow.

Example:
```json
// PUT /v1/settings
{"quiet_hours":[22,7],"digest_hour":8,"ping_cap_per_day":3,"interests":["ai"],"languages":["en"],
 "laya_mode":"shadow","laya_mode_by_niche":{"news_radar":"off"}}
// 200
{"quiet_hours":[22,7],"digest_hour":8,"ping_cap_per_day":3,"interests":["ai"],"languages":["en"],
 "laya_mode":"shadow","laya_mode_by_niche":{"news_radar":"off"},"laya_mode_default":"shadow"}
// PUT with "laya_mode":"on" while stored is "shadow" → 422
{"type":"https://decision-engine/problems/laya-mode-gated","title":"Laya 'on' needs the calibration gate",
 "status":422,"detail":"Switching to 'on' requires the LAYA.md §5 gate and an ADR",
 "errors":[{"field":"body.laya_mode","message":"'on' is not available from the API yet","code":"laya_mode_gated"}]}
```

## Consequences
- An additive v1 change, so `make sdk` must regenerate `SettingsIn`/`SettingsOut`. The existing web form keeps
  working unchanged. `/v1/decide` still uses the env mode only (API.md, unchanged).
- Going to `on` stays an operator action (env `LAYA_MODE`, or a SQL write recorded with the gate ADR). It is never a
  click. Going back to `off`/`shadow` is a click, which is the safe direction.
- Invariant "Laya can never lose an item": unchanged. Every mode keeps the LLM fallback and the human queue.

## Revisit when
- The first niche passes the LAYA.md §5 gate. That ADR may add a gated "enable on" flow, for example one that checks
  a stored shadow-report result.
- Multi-tenant (Phase 8.5): concurrent editors need ETags on settings.

## Migration steps
1. backend-builder (3.5-B4): `schemas/settings.py`, `api/v1/settings.py`, tests in `tests/integration/test_settings_api.py`:
   absent keeps, `null` clears, map replace, `on` change → 422 `laya_mode_gated`, `on` re-send → 200, `on` → `off`
   → 200, unknown niche → 422, `laya_mode_default` mirrors env. No migration (JSONB keys).
2. backend-builder (3.5-B1): `laya_mode` on `GET /v1/niches` rows.
3. backend-builder (3.5-B5): `make sdk`. API.md is updated with this ADR.
4. frontend-builder (3.5b, 3.5e): selectors as above.
5. Rollback: drop the fields. Stored keys are harmless, and `resolve_mode` already reads them.
