# Phase 3 plan — Web app: approval queue

Source: `docs/PLAN.md` Phase 3, `docs/UI_UX.md`, FR-50..56, FR-60/64, FR-70, FR-72, FR-90, FR-112, NFR-10, NFR-11.
State verified 2026-10-14 by reading the code (working tree, uncommitted for 3.4/3.5).

## Goal
The approval queue is the daily tool: keyboard-only, one-keypress approve, undo, bulk, filters, snooze, edit.
Setup screens (History, Niches, Sources, Insights, Settings) exist and talk to the API through the server proxy.

## What already exists (do not redo)
- `apps/web`: Next 16.3.7, React 19.3, Tailwind v4 tokens (`src/app/globals.css`), Auth.js Google + `ALLOWED_EMAILS`
  (`src/auth.ts`), proxy `src/app/api/v1/[...path]/route.ts` + `src/lib/proxy/route-policy.ts` (items list/get/decision/
  activity, settings GET/PUT), flat i18n catalogs `src/messages/{en,hi,pa}.json` via `src/lib/i18n/index.ts`.
- Queue: `components/queue/{QueueView,QueueCard,UndoToast,UrgencyBadge}.tsx`, `lib/queue/{keys,view,undo,confidence}.ts`.
  Keys a, r, 1–5, j, k, o, ? work; `s`/`e` are parsed but no-ops (`QueueView.tsx` switch).
- Item detail page `app/(app)/items/[id]` + `components/item/*`, `lib/item/{decision-form,triage}.ts` (edit form, no raw tab).
- History `components/history/HistoryView.tsx` + `lib/history/query.ts` (search + niche; no verdict/date filters, no Teach).
- Settings `components/settings/SettingsForm.tsx` + `lib/settings/form.ts` (quiet hours, digest hour, ping cap, interests,
  languages). API `GET/PUT /v1/settings` (admin scope, merges keys), `GET /v1/items/{id}/activity`.
- Missing in the API: `GET /v1/niches`, `GET|PUT /v1/niches/{name}`, `GET|POST /v1/sources`, `GET /v1/stats/today`.
  `POST /v1/items/{id}/undo` is documented in API.md but not built (undo is client-side, by design).
- Missing in the web app: queue sort (FR-50: API returns newest first and the UI does not re-sort), filter chips,
  bulk mode, snooze, edit-from-queue, command palette, Inter/Noto fonts, shadcn/ui, Niches/Sources/Insights, Playwright.

## Acceptance (executable)
Run from repo root unless noted.
1. `cd apps/web && npx tsc --noEmit && npx vitest run && npx next build` — all green.
2. `make test && make lint` — green (API changes).
3. `cd apps/web && npx playwright test` — specs `approve`, `keyboard`, `undo`, `snooze`, `bulk`, `a11y` pass:
   - approve: focused card, press `a`, advance clock 10 s → exactly one `POST /api/v1/items/{id}/decision` with
     `{"verdict":"approve"}`, card gone, no second request (approve → done in one keypress).
   - keyboard: queue cleared with `j`/`k`/`a`/`r`/`s`/`1–5`/`?`/`⌘K` and Tab only, no mouse events; focus ring visible
     (computed outline on `:focus-visible`).
   - undo: press `r`, activate Undo by keyboard within 10 s → zero POSTs.
   - a11y: `@axe-core/playwright` on /queue, /items/{id}, /history, /niches, /sources, /insights, /settings → 0 serious/critical.
4. Lighthouse (3.7a, against `make dev` + `make seed`, session cookie from `e2e/helpers/session.ts`):
   `npx lighthouse http://localhost:3000/queue --only-categories=accessibility,performance --preset=desktop
   --extra-headers=./e2e/.lh-headers.json --output=json` → accessibility ≥ 0.95, performance ≥ 0.85. Scores recorded in
   `docs/UI_UX.md` section 8.
5. API: `curl -s -H "Authorization: Bearer $DE_API_KEY" localhost:8000/v1/niches | jq '.data[].name'` lists the starter
   niches; `PUT /v1/niches/inbox` with `"autonomy":"yolo"` → 422 problem+json with `errors[].json_pointer == "/autonomy"`;
   `GET /v1/stats/today` returns counts + per-provider budget; `POST /v1/sources` `{type:"rss",...}` with a non-https URL → 422.
6. `docs/UI_UX.md` section 7 checklist ticked by ui-ux-designer, exceptions listed.

## Steps
Size: S ≤ 150 changed lines, M ≤ 300, L ≤ 400. Each file is owned by one step at a time.

### Gate
**3.0 Verify and commit the working tree** — test-writer, then code-reviewer (read-only), then main session commits. S–M.
- Tests: `components/item/ItemDetailView.test.tsx`, `components/history/HistoryView.test.tsx`,
  `components/settings/SettingsForm.test.tsx`, `lib/history/query.test.ts`, extend `lib/proxy/route-policy.test.ts`
  (settings + activity routes). API: confirm `tests/integration/test_settings_api.py` covers 422s and key merge; add
  an activity-route test (404 for another tenant) if missing.
- FR-56, FR-54 (edit uses the existing decision endpoint), FR-112.
- Commits: `feat(api): settings and item activity routes (FR-43, FR-56)`, `feat(web): item detail, history, settings (3.4, 3.5)`.

### Foundation
**3.1 Design specs for the unbuilt pieces** — ui-ux-designer. S–M. Files: `docs/UI_UX.md` (sections 3, 8 only),
`docs/mocks/{snooze,bulk,palette,niches,sources,insights}.html`. Defines snooze presets (Q2), bulk bar copy + keys,
palette commands, Niches card + YAML editor layout, Sources list + add-RSS form, Insights tiles + budget bars
(accessible palette, no purple). Output includes the exact i18n keys per screen so builders do not invent copy.

**3.2a Fonts, shadcn/ui primitives, i18n split** — frontend-builder. M. NFR-10, NFR-11.
- Files: `apps/web/package.json`, `package-lock.json`, `components.json`, `src/app/layout.tsx`, `src/app/globals.css`
  (font vars only), `src/lib/utils.ts` (`cn`), `src/components/ui/{button,dialog,command,popover,switch,select,tooltip,
  badge}.tsx`, `src/lib/i18n/index.ts`, `src/messages/{en,hi,pa}/{common,queue,item,history,settings}.json` (move existing
  keys, delete flat files), `src/lib/i18n/i18n.test.ts`. Also installs `recharts` and `yaml` now so later parallel steps
  never touch `package.json`.
- Inter + Noto Sans Devanagari + Noto Sans Gurmukhi via `next/font/google` (self-hosted at build, no runtime CDN).
- `translate(locale, key, values)` signature unchanged; catalog = merge of namespace files. Tests: every `en` key exists in
  `hi`/`pa`; no key defined in two namespaces.
- Do not restyle existing components here; later steps adopt primitives in files they already own.

### Backend (sequential chain: all touch `app/api/v1/__init__.py` and the generated SDK)
**3.5-B1 Niches read/write API** — backend-builder. M–L. FR-70, FR-72 (save path only). Needs D3.
- Files: `apps/api/app/api/v1/niches.py`, `apps/api/app/schemas/niches.py`, `apps/api/app/niches/overrides.py` (DB rows →
  `registry.reload(overrides=...)`), `apps/api/tests/integration/test_niches_api.py`, `apps/api/tests/unit/test_niche_overrides.py`.
- `GET /v1/niches` (items:read) → `{data:[{name,label,description,enabled,autonomy,auto_actions,source:"yaml"|"db",version}]}`.
- `GET /v1/niches/{name}` (items:read) → effective config (YAML + DB override) plus its YAML text.
- `PUT /v1/niches/{name}` (admin) → validate with the loader's validator against `schemas/niche.schema.json`; 422 with
  `errors[{json_pointer,message}]` like `/reload`; upsert `niches` row, bump `version`, reload. `generic` cannot be
  disabled; path name must equal body `name`. No migration (table exists).

**3.5-B2 Sources list + add RSS** — backend-builder. M. FR-90. Needs D4 for PATCH.
- Files: `apps/api/app/api/v1/sources.py`, `apps/api/app/schemas/sources.py`, `apps/api/tests/integration/test_sources_api.py`.
- `GET /v1/sources` (items:read) → `{data:[{id,type,name,slug,enabled,niche_hint,last_polled_at,error_count,items_today}]}`;
  never `config`, `secret_enc`, `oauth_enc`.
- `POST /v1/sources` (admin), `type ∈ {rss, google_news}` only; URL/query validated through `connectors/feed_urls.py`
  (https only); slug unique per tenant (409). Other types → 422 "not available yet".
- `PATCH /v1/sources/{id}` `{enabled}` only.

**3.5-B3 Stats today** — backend-builder. M. FR-60, FR-64 (read side).
- Files: `apps/api/app/api/v1/stats.py`, `apps/api/app/schemas/stats.py`, `apps/api/tests/integration/test_stats_api.py`.
- `GET /v1/stats/today` (items:read) → `{date, items_in, decided, auto_handled, discarded, by_status, by_niche,
  llm:[{provider, requests_used, requests_limit, tokens_used, tokens_limit}], laya:{mode, healthy}}`. Budgets via
  `llm/budgets.get_budget_store()`; counts from `items`/`decisions`/`llm_usage` for the UTC day; Laya health from the
  cached deep-health result, never a live Laya call per request.

**3.5-B4 Laya mode in settings** — backend-builder. S. Blocked on D2.
- Files: `apps/api/app/schemas/settings.py`, `apps/api/app/api/v1/settings.py`, `apps/api/tests/integration/test_settings_api.py`.
- Add `laya_mode: "off"|"shadow"` and `laya_mode_by_niche: {name: "off"|"shadow"}` to `SettingsIn/Out` (keys already read by
  `triage/modes.resolve_mode`). `on` → 422 from this endpoint.

**3.5-B5 Regenerate SDKs + API docs** — backend-builder. S. `make sdk` → `packages/openapi.json`,
`packages/client-ts/src/schema.d.ts`, `packages/client-py/**/_generated/**`; `docs/API.md` (niches, sources, stats, settings
fields; `POST /v1/items/{id}/undo` marked LATER per D1).

### Queue (sequential chain: all touch `QueueView.tsx`)
**3.3a Sort + filter chips** — frontend-builder. M. FR-50.
- Files: `src/lib/queue/order.ts` (+ test): pure `sortQueue(items)` urgency desc → deadline asc (nulls last) →
  `created_at` asc; `src/lib/queue/filters.ts` (+ test): chips from loaded items' niche/source, `applyFilters`;
  `src/components/queue/FilterChips.tsx`; `QueueView.tsx`; `src/lib/api/items.ts` (`PENDING_LIMIT` → 100, proxy max; Q4).
- Chip state in URL search params (`?niche=&source=`).

**3.3b Snooze (`s`) and edit (`e`)** — frontend-builder. M. FR-52, FR-53, FR-54. Blocked on Q2.
- Files: `src/lib/queue/snooze.ts` (+ test): pure `snoozePresets(now, timeZone)` → ISO UTC; `src/components/queue/SnoozeMenu.tsx`
  (keys 1–4 inside, Esc closes, "pick" = `datetime-local`, must be future); `src/lib/queue/undo.ts` (`PendingDecision` gains
  `snoozeUntil?`); `QueueView.tsx`; `src/lib/api/items.ts` (`postDecision` takes a `DecisionBody`);
  `src/components/item/DecisionPanel.tsx` (read `?edit=1` only).
- Snooze goes through the same 10 s undo hold. `e` navigates to `/items/{id}?edit=1`.

**3.3c Bulk mode** — frontend-builder. M. FR-55, FR-53.
- Files: `src/lib/queue/bulk.ts` (+ test): eligible = urgency < 2, has recommended option, risk not scam/phishing (Q3);
  `src/components/queue/BulkBar.tsx`; `QueueCard.tsx` (checkbox); `QueueView.tsx`; `src/lib/queue/undo.ts`
  (`scheduleMany`, `cancelBatch`).
- One toast "Approved 8 · Undo" undoes the whole batch; after the window, send with concurrency 3; failures return to
  the queue with the existing failed banner. Keys from 3.1.

### Parallel with the queue chain
**3.3d Command palette (⌘K)** — frontend-builder. S–M.
- Files: `src/components/CommandPalette.tsx`, `src/lib/palette/commands.ts` (+ test), `src/app/(app)/layout.tsx`.
- Commands: go to each screen, show shortcuts, search items (→ History with `q`). Item actions stay on queue keys, so this
  step never touches `QueueView.tsx` (which already ignores modified keys).

**3.4 Item detail: finish** — frontend-builder. S–M. FR-51, FR-54. After 3.3b (shares `components/item/`).
- Files: `src/components/item/{ItemDetailView,ItemTabs}.tsx`, `src/lib/item/*` (+ tests).
- Tabs: Decision · Content · Triage (all Laya answers, mode, model, latency from `summarizeTriage`) · Activity.
  Raw tab stays omitted (Q1). Full page, not drawer (D5).

### Setup screens (after 3.5-B5 and 3.2a)
**3.5a Proxy routes + nav** — frontend-builder. S. Files: `src/lib/proxy/route-policy.ts` (+ test),
`src/app/api/v1/[...path]/route.ts` (export PATCH), `src/components/AppNav.tsx`, `src/messages/*/common.json` (nav labels).
- Allow: `GET niches`, `GET|PUT niches/{name}` (name `^[a-z][a-z0-9_]{1,39}$`), `GET|POST sources`, `PATCH sources/{uuid}`
  (add PATCH to `ProxyMethod`/`BODY_METHODS`), `GET stats/today`. Everything else stays 404/405.

Then in parallel (disjoint files; each owns `src/messages/{en,hi,pa}/<screen>.json`):

**3.5b Niches** — frontend-builder. L. FR-70, FR-72 (edit/save). `src/app/(app)/niches/{page.tsx,[name]/page.tsx}`,
`src/components/niches/*`, `src/lib/niches/*` (+ tests), `src/lib/api/niches.ts`. Cards: enabled switch, autonomy select,
Laya mode (off/shadow; `on` disabled with "needs calibration"), version. Detail: form (description, autonomy, auto_actions)
+ "Advanced: YAML" editor; debounced YAML syntax check client-side, schema errors from PUT 422 shown by json_pointer (D6).
Saving `autonomy: auto` opens a confirm dialog listing `auto_actions`.

**3.5c Sources** — frontend-builder. M. FR-90. `src/app/(app)/sources/page.tsx`, `src/components/sources/*`,
`src/lib/sources/*` (+ tests), `src/lib/api/sources.ts`. List: health (icon + text, not color only), last sync, items today,
error count, enable switch; "Add RSS / Google News query" form. Other types shown as "coming later", no buttons.

**3.5d Insights** — frontend-builder. M. FR-64. `src/app/(app)/insights/page.tsx`, `src/components/insights/*`,
`src/lib/insights/*` (+ tests), `src/lib/api/stats.ts`. Tiles: in / decided / auto-handled / discarded; per-provider
budget bars (Recharts, warning at 80 %); Laya mode + health. Time saved and Laya agreement omitted (Q6).

**3.5e Settings: Laya mode** — frontend-builder. S. After 3.5-B4. `src/components/settings/SettingsForm.tsx`,
`src/lib/settings/form.ts` (+ test), `src/messages/*/settings.json`. Global Laya mode off/shadow. Autonomy lives on Niches.

### Tests and review
**3.6a Playwright setup** — test-writer. S–M. `apps/web/package.json` (@playwright/test, @axe-core/playwright, script `e2e`),
`playwright.config.ts`, `e2e/helpers/{session.ts,api-mock.ts,fixtures.ts}`. Session: mint an Auth.js JWT cookie with a test
`AUTH_SECRET` for an allow-listed email via `next-auth/jwt` `encode` (D7). API mocked with `page.route('**/api/v1/**')`;
synthetic fixtures only; time via `page.clock`; `webServer` = `next build && next start` with test env.

**3.6b Specs** — test-writer. M. `e2e/{approve,keyboard,undo,snooze,bulk,a11y}.spec.ts` (acceptance 3);
update `docs/TEST_MATRIX.md` rows FR-50..56.

**3.7a UX review** — ui-ux-designer. S. UI_UX §7 checklist at 360 px, 200 % zoom, hi, pa; Lighthouse (acceptance 4);
screenshots of synthetic data to `docs/mocks/review-phase-3/`. Output: fix list in `docs/UI_UX.md` §8.

**3.7b Fixes** — frontend-builder. ≤ M. Files named by 3.7a. Then code-reviewer on the phase diff; docs-keeper ticks PLAN.md.

## Parallel groups (∥ = run together)
- G0: 3.0 (gate; commit before anything edits these files)
- G1: 3.1 ∥ 3.2a ∥ 3.5-B1
- G2: 3.3a ∥ 3.3d ∥ 3.5-B2
- G3: 3.3b ∥ 3.5-B3
- G4: 3.3c ∥ 3.4 ∥ 3.5-B4 (skip B4 if D2 rejected), then 3.5-B5
- G5: 3.5a
- G6: 3.5b ∥ 3.5c ∥ 3.5d ∥ 3.5e
- G7: 3.6a → 3.6b
- G8: 3.7a → 3.7b → code-reviewer → docs-keeper
Hard orderings: 3.3a→3.3b→3.3c (`QueueView.tsx`, `undo.ts`, `items.ts`); 3.3b→3.4 (`components/item/`);
B1→B2→B3→B4→B5 (`api/v1/__init__.py`, SDK); 3.2a before any step using `components/ui` or namespaced messages;
3.2a→3.6a (`package.json`). 3.3a–c start after 3.2a only if they need primitives; otherwise G2 may start with G1.

## Design decisions
- D1 Undo stays client-side (held 10 s, then sent); API.md's `POST /items/{id}/undo` marked LATER. Closing the tab inside
  the window drops the decision and the item stays in the queue (safe). **Architect: confirm.**
- D2 Laya mode editable in the web UI as `off`/`shadow` only (global + per niche in `tenant_settings`); `on` refused until
  the LAYA.md calibration gate + ADR. **Architect: contract change to `SettingsIn`.**
- D3 Niche overrides: PUT reloads the API process's registry; the worker must also see DB overrides (reload when
  `niches.version` changes, or periodic). **Architect: choose mechanism before B1.**
- D4 `PATCH /v1/sources/{id}` (enable switch) is not in API.md. **Architect: approve or drop the switch.**
- D5 Item detail stays a full page (UI_UX says drawer on desktop); revisit in 3.7a. An intercepting-route drawer is size L.
- D6 One validator: client checks YAML syntax only (`yaml` package); schema validation is server-side via PUT 422, no
  browser copy of the schema. **Architect: confirm no dry-run validate endpoint is wanted.**
- D7 E2E auth by minting a session cookie in tests; no test-only login route in `src/`.
- D8 New web deps, all named in UI_UX §5 or the stack (no ADR): shadcn/ui (Radix, cva, tailwind-merge, clsx, lucide-react,
  cmdk), recharts, yaml, @playwright/test, @axe-core/playwright. Exact versions pinned.
- D9 The proxy uses one `DE_API_KEY` that already has `admin` (settings PUT), so every allow-listed Google user can edit
  niches and sources. Fine for single tenant (FR-110); security-auditor to note before deploy.
- D10 Messages split into per-screen namespace files so screen steps can run in parallel.

## Questions for the owner
- Q1 (non-blocking) Raw JSON tab: keep omitted (raw bodies are private; API does not return them), or add a redacted
  `GET /v1/items/{id}/raw` in a later phase?
- Q2 (**blocks 3.3b**) Snooze presets: "later today" = +3 h, "tomorrow" = 09:00, "next week" = Monday 09:00, in the
  browser's time zone (Settings has no time zone yet). OK, or always Asia/Kolkata?
- Q3 (non-blocking) Bulk eligibility = urgency below 2 and not scam/phishing. Right?
- Q4 (non-blocking) The queue loads up to 100 waiting items and sorts in the browser. If more than 100 can wait, the API
  needs an `order=queue` parameter (architect).
- Q5 (non-blocking) Confirm the niche "Test with an example" box (spends LLM budget via `/v1/decide`) and the wizard (8.4)
  stay out of Phase 3.
- Q6 (non-blocking) Insights "time saved" needs a minutes-per-decision figure and "Laya agreement %" needs a shadow-report
  API. Drop both for Phase 3?
- Q7 (non-blocking) Who reviews Hindi/Punjabi strings, and does it block the Phase 3 tick?
- Q8 (**blocks the live sign-in check only**) A Google OAuth client (redirect `http://localhost:3000/api/auth/callback/google`).

## Out of scope
Webhook/Gmail/Instagram/Telegram/CSV source setup (Phases 4–5); niche wizard and `/v1/niches/draft` (8.4); niche test box;
History verdict/decided_by/date filters and "Teach" (no correction API yet); raw JSON tab; server-side undo; Settings
sections for API keys, webhook subscriptions, privacy, danger zone; mobile (Phase 6); farmer mode (Phase 7).

## Summary
- 20 steps: gate 3.0; foundation 3.1, 3.2a; backend 3.5-B1..B5; queue 3.3a–d, 3.4; screens 3.5a–e; e2e 3.6a–b; review 3.7a–b.
- Groups: G0 → G1 (3.1 ∥ 3.2a ∥ B1) → G2–G4 (queue chain ∥ backend chain ∥ palette) → G5 3.5a → G6 (4 screens ∥) → G7 e2e → G8 review.
- Architect before B1/B2/B4: D1, D2, D3, D4, D6. Owner before 3.3b: Q2.
- First agent: test-writer on 3.0, then code-reviewer, then commit the working tree.
- Next: architect on D1–D4 and D6 while 3.1 and 3.2a run.
