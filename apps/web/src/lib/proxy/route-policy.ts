/**
 * Which API calls the browser may make through the server proxy. Anything not listed is refused,
 * so the proxy can never be used as a general gateway to the Decision Engine API.
 */

export const ALLOWED_LIST_PARAMS = ["status", "niche", "source", "q", "cursor", "limit"] as const;
export const MAX_LIST_LIMIT = 100;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type ProxyPlan =
  | { ok: true; method: "GET" | "POST"; path: string; search: string }
  | { ok: false; status: 404 | 405 };

function isUuid(value: string | undefined): value is string {
  return value !== undefined && UUID_PATTERN.test(value);
}

function clampLimit(value: string): string {
  const parsed = Number.parseInt(value, 10);
  const limit = Math.min(Math.max(Number.isNaN(parsed) ? 1 : parsed, 1), MAX_LIST_LIMIT);
  return String(limit);
}

/** Keep only known list parameters and clamp `limit`; everything else is dropped. */
export function listSearch(params: URLSearchParams): string {
  const kept = new URLSearchParams();
  for (const name of ALLOWED_LIST_PARAMS) {
    const value = params.get(name);
    if (value === null || value === "") {
      continue;
    }
    kept.set(name, name === "limit" ? clampLimit(value) : value);
  }
  const query = kept.toString();
  return query ? `?${query}` : "";
}

export function planProxy(
  method: string,
  segments: readonly string[],
  params: URLSearchParams,
): ProxyPlan {
  const [resource, id, action, ...rest] = segments;
  if (resource !== "items" || rest.length > 0) {
    return { ok: false, status: 404 };
  }
  if (segments.length === 1) {
    return method === "GET"
      ? { ok: true, method: "GET", path: "/v1/items", search: listSearch(params) }
      : { ok: false, status: 405 };
  }
  if (!isUuid(id)) {
    return { ok: false, status: 404 };
  }
  if (segments.length === 2) {
    return method === "GET"
      ? { ok: true, method: "GET", path: `/v1/items/${id}`, search: "" }
      : { ok: false, status: 405 };
  }
  if (action === "decision" && segments.length === 3) {
    return method === "POST"
      ? { ok: true, method: "POST", path: `/v1/items/${id}/decision`, search: "" }
      : { ok: false, status: 405 };
  }
  return { ok: false, status: 404 };
}
