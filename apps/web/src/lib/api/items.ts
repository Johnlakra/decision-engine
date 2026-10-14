import type { components } from "@decision-engine/client";
import type { Verdict } from "@/lib/queue/undo";

/** Browser-side calls through the server proxy (`/api/v1`). No API key is ever sent from here. */

export type ItemOut = components["schemas"]["DecisionItemOut"];
export type ItemPage = components["schemas"]["ItemPage"];

export const API_BASE = "/api/v1";
export const PENDING_LIMIT = 50;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
    },
  });
  if (!response.ok) {
    throw new ApiError(response.status);
  }
  return (await response.json()) as T;
}

export function fetchPendingItems(): Promise<ItemPage> {
  return requestJson<ItemPage>(`/items?status=awaiting_approval&limit=${PENDING_LIMIT}`);
}

export function postDecision(itemId: string, verdict: Verdict, option?: string): Promise<unknown> {
  return requestJson(`/items/${encodeURIComponent(itemId)}/decision`, {
    method: "POST",
    body: JSON.stringify(option ? { verdict, option } : { verdict }),
  });
}
