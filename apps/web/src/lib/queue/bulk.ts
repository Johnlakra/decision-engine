/**
 * Bulk approval rules (phase 3 Q3, owner default): urgency below 2, a recommended option that
 * exists, and a risk that is not scam or phishing. Pure: items in, entries out.
 */
import type { ItemOut } from "@/lib/api/items";
import type { BatchEntry } from "./undo";
import { optionsOf, recommendedIdOf } from "./view";

const BULK_MAX_URGENCY = 1;
const BLOCKED_RISKS: ReadonlySet<string> = new Set(["scam", "phishing"]);

function recommendedOptionOf(item: ItemOut): string | null {
  const recommended = recommendedIdOf(item.decision);
  if (recommended === null) {
    return null;
  }
  return optionsOf(item.decision).some((option) => option.id === recommended) ? recommended : null;
}

export function isBulkEligible(item: ItemOut): boolean {
  if ((item.urgency ?? 0) > BULK_MAX_URGENCY) {
    return false;
  }
  if (item.risk && BLOCKED_RISKS.has(item.risk.toLowerCase())) {
    return false;
  }
  return recommendedOptionOf(item) !== null;
}

export function eligibleItems(items: readonly ItemOut[]): ItemOut[] {
  return items.filter(isBulkEligible);
}

/** One approve per selected, eligible item, each with its recommended option. */
export function buildBulkBatch(items: readonly ItemOut[], selected: ReadonlySet<string>): BatchEntry[] {
  return items.flatMap((item): BatchEntry[] => {
    const option = selected.has(item.id) && isBulkEligible(item) ? recommendedOptionOf(item) : null;
    return option === null ? [] : [{ itemId: item.id, option }];
  });
}
