import type { ItemOut } from "@/lib/api/items";

/**
 * Queue filter chips (FR-50). The active chips live in the URL (`?niche=&source=`), so a filtered
 * queue survives a reload. Pure: every function returns new values.
 */

export interface QueueFilter {
  readonly niche: string | null;
  readonly source: string | null;
}

export interface FilterChoices {
  readonly niches: readonly string[];
  readonly sources: readonly string[];
}

export const NO_FILTER: QueueFilter = { niche: null, source: null };

function distinctSorted(values: readonly (string | null | undefined)[]): string[] {
  const present = values.filter((value): value is string => typeof value === "string" && value !== "");
  return [...new Set(present)].sort();
}

/** Chips come from every loaded item, so they stay visible while a filter is active. */
export function filterChoices(items: readonly ItemOut[]): FilterChoices {
  return {
    niches: distinctSorted(items.map((item) => item.niche)),
    sources: distinctSorted(items.map((item) => item.source)),
  };
}

export function applyFilters(items: readonly ItemOut[], filter: QueueFilter): ItemOut[] {
  return items.filter(
    (item) =>
      (filter.niche === null || item.niche === filter.niche) &&
      (filter.source === null || item.source === filter.source),
  );
}

export function filterFromParams(params: URLSearchParams): QueueFilter {
  return { niche: params.get("niche") || null, source: params.get("source") || null };
}

export function paramsWithFilter(params: URLSearchParams, filter: QueueFilter): URLSearchParams {
  const next = new URLSearchParams(params);
  if (filter.niche) {
    next.set("niche", filter.niche);
  } else {
    next.delete("niche");
  }
  if (filter.source) {
    next.set("source", filter.source);
  } else {
    next.delete("source");
  }
  return next;
}
