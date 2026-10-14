# 0007 — Undo is a client-side hold; `POST /v1/items/{id}/undo` is LATER

**Status:** accepted · 2026-10-14 · Requirements: FR-33, FR-50, FR-53, FR-55, NFR-10 · Plan: phase 3 D1, steps 3.3a–c, 3.5-B5

## Context
- FR-53: "Undo for 10 s after any queue action." API.md lists `POST /v1/items/{id}/undo — within 10 s of a decision`,
  but no route exists. The web queue (`lib/queue/undo.ts`, `UndoToast.tsx`) already holds each decision in the browser
  for 10 s and only then calls `POST /v1/items/{id}/decision`.
- `approve`/`edit` run the niche's allowed actions **inline** and return `done` (API.md). Some actions are irreversible
  (send, reply, post). Once the decision request has run, undo cannot recall a sent email.
- Telegram buttons (`de:a:<id>`, `de:r:<id>`) resume an item at once. They are not part of "the queue".
- A double submit already gives one `200` and one `409` (`not-awaiting-approval` / `item-busy`).

## Options considered
| | (a) Client-side hold (10 s in the client, then one POST) | (b) Server-side delayed commit (POST records a pending decision, a job applies it after 10 s, `/undo` cancels) | (c) Server-side compensating undo (apply now, `/undo` reverses) |
|---|---|---|---|
| Irreversible actions | Never run inside the window | Never run inside the window | Cannot be undone once sent: breaks the promise |
| New server state | None | `pending_decisions` table or job + migration, a cancel race to handle, a new item status | Reversal per action (`reversible` flag), partial failures |
| Closing the tab inside the window | Decision dropped; the item stays `awaiting_approval` (safe: nothing lost, nothing sent) | Decision still applied | Decision applied |
| Free-tier cost / ops | 0 extra DB writes or jobs | One job and two writes per decision; keeps Neon compute awake longer | Extra action calls |
| Other clients | Mobile (Phase 6) repeats the same ~60-line hold | Shared by every client | Shared |

## Decision
**(a) Client-side hold.** Every queue client holds a decision (approve, reject, edit, snooze, bulk) for **10 s** and
then sends exactly one `POST /v1/items/{id}/decision`. Undo inside the window cancels the timer and sends nothing.
`POST /v1/items/{id}/undo` stays in API.md marked **LATER (not built; see ADR 0007)**.

Client rules (web now, mobile in Phase 6):
1. The window is 10 s from the keypress or tap. One toast per action, and one toast per bulk batch (undo cancels the
   whole batch).
2. After the window, a `409` from the decision POST means another client (for example Telegram) already handled the
   item. Remove the card quietly and do not show an error. `422` and `5xx` put the card back with the failed banner.
3. Leaving the page drops held decisions. The web may show a `beforeunload` prompt while anything is held. It never
   sends a held decision with `sendBeacon` (that would make undo unreliable).
4. Telegram buttons stay immediate. FR-53 covers the queue UIs. Telegram only offers approve with the recommended
   option and reject, under the niche's autonomy rules.

## Consequences
- No API, schema or migration change. The SDKs are unchanged.
- An approval reaches the server 10 s after the keypress. That is acceptable for a human-paced queue.
- The undo logic exists twice (web, mobile), so both clients must test it (Playwright `undo.spec.ts`, Jest in Phase 6).
- Invariant check: the hold sits before the approval step, so irreversible actions still pass `interrupt()` and the
  human's decision. Nothing is lost when a tab closes, because the item stays in the queue.

## Revisit when
- A non-interactive client (API caller, a voice flow) needs undo. Then build (b) with its own ADR.
- Users report lost decisions from closed tabs.

## Migration steps
1. architect: API.md marks `/undo` LATER (done with this ADR).
2. frontend-builder (3.3b, 3.3c): keep `lib/queue/undo.ts` as the only send path. Add the `409` = "already handled" rule
   and `scheduleMany`/`cancelBatch`.
3. test-writer (3.6b): `undo.spec.ts` (zero POSTs after undo) and `approve.spec.ts` (exactly one POST after 10 s).
4. Rollback: none needed. Nothing is stored server-side.
