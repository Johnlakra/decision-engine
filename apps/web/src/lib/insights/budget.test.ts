import { describe, expect, it } from "vitest";
import { budgetView, nicheCounts, BUDGET_WARNING_RATIO } from "./budget";

describe("budgetView", () => {
  it("computes percent from requests_used over requests_limit", () => {
    expect(budgetView({ provider: "gemini", requests_used: 120, requests_limit: 500, tokens_used: 1, tokens_limit: null })).toEqual({
      provider: "gemini",
      used: 120,
      limit: 500,
      percent: 24,
      level: "ok",
    });
  });

  it("warns at 80 percent and is exhausted at 100", () => {
    const at = (used: number) =>
      budgetView({ provider: "p", requests_used: used, requests_limit: 100, tokens_used: 0, tokens_limit: null }).level;
    expect(BUDGET_WARNING_RATIO).toBe(0.8);
    expect(at(79)).toBe("ok");
    expect(at(80)).toBe("warning");
    expect(at(100)).toBe("exhausted");
  });

  it("clamps the bar width and handles a missing or zero limit", () => {
    expect(budgetView({ provider: "p", requests_used: 150, requests_limit: 100, tokens_used: 0, tokens_limit: null }).percent).toBe(100);
    const none = budgetView({ provider: "p", requests_used: 7, requests_limit: null, tokens_used: 0, tokens_limit: null });
    expect(none).toMatchObject({ limit: null, percent: 0, level: "unlimited" });
    expect(budgetView({ provider: "p", requests_used: 7, requests_limit: 0, tokens_used: 0, tokens_limit: null }).level).toBe("unlimited");
  });
});

describe("nicheCounts", () => {
  it("sorts by count descending, then name", () => {
    expect(nicheCounts({ b: 2, a: 2, c: 9 })).toEqual([
      { name: "c", count: 9 },
      { name: "a", count: 2 },
      { name: "b", count: 2 },
    ]);
  });
});
