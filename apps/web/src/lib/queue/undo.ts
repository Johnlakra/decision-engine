/**
 * Undo window for queue actions (docs/UI_UX.md: "Archived · Undo for 10 s").
 * The API has no undo, so a decision is held here and sent only when its window closes.
 * Pure and immutable: every function returns a new list.
 */

export const UNDO_WINDOW_MS = 10_000;

export type Verdict = "approve" | "reject" | "snooze";

export interface PendingDecision {
  readonly itemId: string;
  readonly verdict: Verdict;
  readonly option: string | undefined;
  /** ISO 8601 UTC; set only when the verdict is snooze. */
  readonly snoozeUntil?: string;
  readonly dueAt: number;
  /** Set on bulk approvals so one Undo cancels the whole batch. */
  readonly batchId?: string;
}

export function scheduleDecision(
  pending: readonly PendingDecision[],
  itemId: string,
  verdict: Verdict,
  now: number,
  option?: string,
  snoozeUntil?: string,
): PendingDecision[] {
  const next: PendingDecision = {
    itemId,
    verdict,
    option,
    dueAt: now + UNDO_WINDOW_MS,
    ...(snoozeUntil ? { snoozeUntil } : {}),
  };
  return [...pending.filter((entry) => entry.itemId !== itemId), next];
}

export function cancelDecision(
  pending: readonly PendingDecision[],
  itemId: string,
): PendingDecision[] {
  return pending.filter((entry) => entry.itemId !== itemId);
}

export function dueDecisions(pending: readonly PendingDecision[], now: number): PendingDecision[] {
  return pending.filter((entry) => entry.dueAt <= now);
}

export interface BatchEntry {
  readonly itemId: string;
  readonly option: string;
}

/** Hold several approvals under one batch id, all due at the same moment. */
export function scheduleMany(
  pending: readonly PendingDecision[],
  entries: readonly BatchEntry[],
  now: number,
  batchId: string,
): PendingDecision[] {
  const ids = new Set(entries.map((entry) => entry.itemId));
  const held: PendingDecision[] = entries.map((entry) => ({
    itemId: entry.itemId,
    verdict: "approve",
    option: entry.option,
    dueAt: now + UNDO_WINDOW_MS,
    batchId,
  }));
  return [...pending.filter((entry) => !ids.has(entry.itemId)), ...held];
}

export function cancelBatch(pending: readonly PendingDecision[], batchId: string): PendingDecision[] {
  return pending.filter((entry) => entry.batchId !== batchId);
}
