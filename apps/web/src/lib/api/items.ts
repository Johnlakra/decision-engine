import type { components } from "@decision-engine/client";
import { requestJson } from "@/lib/api/request";

export { ApiError } from "@/lib/api/request";

export type ItemOut = components["schemas"]["DecisionItemOut"];
export type ItemPage = components["schemas"]["ItemPage"];
export type ActivityOut = components["schemas"]["ActivityOut"];
export type DecisionBody = components["schemas"]["DecisionIn"];

export const PENDING_LIMIT = 100;

export function fetchPendingItems(): Promise<ItemPage> {
  return requestJson<ItemPage>("GET", `/items?status=awaiting_approval&limit=${PENDING_LIMIT}`);
}

export function fetchItem(itemId: string): Promise<ItemOut> {
  return requestJson<ItemOut>("GET", `/items/${encodeURIComponent(itemId)}`);
}

export function fetchActivity(itemId: string): Promise<ActivityOut> {
  return requestJson<ActivityOut>("GET", `/items/${encodeURIComponent(itemId)}/activity`);
}

export function postDecisionBody(itemId: string, body: DecisionBody): Promise<unknown> {
  return requestJson("POST", `/items/${encodeURIComponent(itemId)}/decision`, body);
}
