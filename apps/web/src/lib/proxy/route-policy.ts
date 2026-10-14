/**
 * Which API calls the browser may make through the server proxy. Anything not listed is refused,
 * so the proxy can never be used as a general gateway to the Decision Engine API.
 */
import { isNicheName } from "@/lib/niches/name";

export const ALLOWED_LIST_PARAMS = ["status", "niche", "source", "q", "cursor", "limit"] as const;
export const MAX_LIST_LIMIT = 100;
/** `POST /v1/niches/reload` is not proxied, so its name must never be read as a niche. */
const RESERVED_NICHE_NAMES: readonly string[] = ["reload"];
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type ProxyMethod = "GET" | "POST" | "PUT";

export type ProxyPlan =
  | { ok: true; method: ProxyMethod; path: string; search: string }
  | { ok: false; status: 404 | 405 };

/** Methods that carry a JSON body through the proxy. */
export const BODY_METHODS: readonly ProxyMethod[] = ["POST", "PUT"];

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

function only(method: string, allowed: ProxyMethod, plan: ProxyPlan): ProxyPlan {
  return method === allowed ? plan : { ok: false, status: 405 };
}

function planNiches(method: string, segments: readonly string[]): ProxyPlan {
  if (segments.length === 1) {
    return only(method, "GET", { ok: true, method: "GET", path: "/v1/niches", search: "" });
  }
  const name = segments[1];
  const isSlug = name !== undefined && isNicheName(name) && !RESERVED_NICHE_NAMES.includes(name);
  if (segments.length !== 2 || !isSlug) {
    return { ok: false, status: 404 };
  }
  const path = `/v1/niches/${name}`;
  return method === "GET" || method === "PUT"
    ? { ok: true, method, path, search: "" }
    : { ok: false, status: 405 };
}

export function planProxy(
  method: string,
  segments: readonly string[],
  params: URLSearchParams,
): ProxyPlan {
  const [resource, id, action, ...rest] = segments;
  if (resource === "settings" && segments.length === 1) {
    const path = "/v1/settings";
    return method === "GET" || method === "PUT"
      ? { ok: true, method, path, search: "" }
      : { ok: false, status: 405 };
  }
  if (resource === "niches") {
    return planNiches(method, segments);
  }
  if (resource !== "items" || rest.length > 0) {
    return { ok: false, status: 404 };
  }
  if (segments.length === 1) {
    return only(method, "GET", { ok: true, method: "GET", path: "/v1/items", search: listSearch(params) });
  }
  if (!isUuid(id)) {
    return { ok: false, status: 404 };
  }
  if (segments.length === 2) {
    return only(method, "GET", { ok: true, method: "GET", path: `/v1/items/${id}`, search: "" });
  }
  if (segments.length === 3 && action === "decision") {
    return only(method, "POST", { ok: true, method: "POST", path: `/v1/items/${id}/decision`, search: "" });
  }
  if (segments.length === 3 && action === "activity") {
    return only(method, "GET", { ok: true, method: "GET", path: `/v1/items/${id}/activity`, search: "" });
  }
  return { ok: false, status: 404 };
}
