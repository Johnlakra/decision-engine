import type { LlmBudget } from "@/lib/api/stats";

/** Budget bar maths for the Insights screen (FR-64). Uses requests_used over requests_limit. */

export const BUDGET_WARNING_RATIO = 0.8;
const PERCENT = 100;

export type BudgetLevel = "ok" | "warning" | "exhausted" | "unlimited";

export interface BudgetView {
  readonly provider: string;
  readonly used: number;
  readonly limit: number | null;
  /** Whole percent for the bar width, clamped to 0..100. */
  readonly percent: number;
  readonly level: BudgetLevel;
}

export function budgetView(budget: LlmBudget): BudgetView {
  const { provider, requests_used: used, requests_limit: limit } = budget;
  if (limit === null || limit <= 0) {
    return { provider, used, limit: null, percent: 0, level: "unlimited" };
  }
  const ratio = used / limit;
  const level: BudgetLevel = ratio >= 1 ? "exhausted" : ratio >= BUDGET_WARNING_RATIO ? "warning" : "ok";
  return { provider, used, limit, percent: Math.min(Math.round(ratio * PERCENT), PERCENT), level };
}

export function nicheCounts(
  byNiche: Readonly<Record<string, number>>,
): { readonly name: string; readonly count: number }[] {
  return Object.entries(byNiche)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}
