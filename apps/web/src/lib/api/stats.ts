import type { components } from "@decision-engine/client";
import { requestJson } from "@/lib/api/request";

export type StatsToday = components["schemas"]["StatsToday"];
export type LlmBudget = components["schemas"]["LlmBudgetOut"];

export function fetchStatsToday(): Promise<StatsToday> {
  return requestJson<StatsToday>("GET", "/stats/today");
}
