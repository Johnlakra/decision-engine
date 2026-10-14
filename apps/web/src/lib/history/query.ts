/** Builds the list path for the History screen. Pure. Only the proxy's allowed filters are sent. */

export const HISTORY_PAGE_SIZE = 25;

export interface HistoryFilters {
  readonly niche: string;
  readonly source: string;
  readonly q: string;
}

export function historyPath(filters: HistoryFilters, cursor: string | null): string {
  const params = new URLSearchParams();
  const entries: [string, string][] = [
    ["niche", filters.niche.trim()],
    ["source", filters.source.trim()],
    ["q", filters.q.trim()],
    ["cursor", cursor ?? ""],
  ];
  for (const [name, value] of entries) {
    if (value !== "") {
      params.set(name, value);
    }
  }
  params.set("limit", String(HISTORY_PAGE_SIZE));
  return `/items?${params.toString()}`;
}
