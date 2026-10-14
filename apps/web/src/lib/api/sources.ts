import type { components } from "@decision-engine/client";
import { requestJson } from "@/lib/api/request";
import type { SourceCreate } from "@/lib/sources/form";

export { ApiError } from "@/lib/api/request";

export type SourceOut = components["schemas"]["SourceOut"];
export type SourceList = components["schemas"]["SourceList"];

export function fetchSources(): Promise<SourceList> {
  return requestJson<SourceList>("GET", "/sources");
}

export function createSource(body: SourceCreate): Promise<SourceOut> {
  return requestJson<SourceOut>("POST", "/sources", body);
}

/** Only `enabled` can change (ADR 0010), so that is the only key sent. */
export function setSourceEnabled(id: string, enabled: boolean): Promise<SourceOut> {
  return requestJson<SourceOut>("PATCH", `/sources/${encodeURIComponent(id)}`, { enabled });
}
