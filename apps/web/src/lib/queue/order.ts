import type { ItemOut } from "@/lib/api/items";

/**
 * Queue order (FR-50): urgency high to low, then the earliest deadline (items with no deadline
 * last), then the oldest item first. Pure; returns a new array.
 */

function compareDeadline(a: ItemOut, b: ItemOut): number {
  const aTime = a.deadline_at ? Date.parse(a.deadline_at) : null;
  const bTime = b.deadline_at ? Date.parse(b.deadline_at) : null;
  if (aTime === null || bTime === null) {
    return aTime === bTime ? 0 : aTime === null ? 1 : -1;
  }
  return aTime - bTime;
}

function compareQueue(a: ItemOut, b: ItemOut): number {
  const urgency = (b.urgency ?? 0) - (a.urgency ?? 0);
  return urgency !== 0 ? urgency : compareDeadline(a, b) || Date.parse(a.created_at) - Date.parse(b.created_at);
}

export function sortQueue(items: readonly ItemOut[]): ItemOut[] {
  return [...items].sort(compareQueue);
}
