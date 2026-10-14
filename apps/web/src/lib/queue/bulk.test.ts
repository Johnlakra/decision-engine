import { describe, expect, it } from "vitest";
import type { ItemOut } from "@/lib/api/items";
import { buildBulkBatch, eligibleItems, isBulkEligible } from "./bulk";

function item(id: string, overrides: Partial<ItemOut> = {}): ItemOut {
  return {
    id,
    urgency: 0,
    risk: "none",
    decision: { options: [{ id: "A", label: "Go" }], recommended: "A" },
    ...overrides,
  } as ItemOut;
}

describe("isBulkEligible", () => {
  it("accepts low urgency with a recommendation and a safe risk", () => {
    expect(isBulkEligible(item("1", { urgency: 1 }))).toBe(true);
  });

  it("treats a missing urgency as low", () => {
    expect(isBulkEligible(item("1", { urgency: undefined }))).toBe(true);
  });

  it("rejects urgency 2 and above", () => {
    expect(isBulkEligible(item("1", { urgency: 2 }))).toBe(false);
    expect(isBulkEligible(item("1", { urgency: 3 }))).toBe(false);
  });

  it("rejects scam and phishing risk, any case", () => {
    expect(isBulkEligible(item("1", { risk: "scam" }))).toBe(false);
    expect(isBulkEligible(item("1", { risk: "Phishing" }))).toBe(false);
  });

  it("rejects items without a recommended option that exists", () => {
    expect(isBulkEligible(item("1", { decision: { options: [{ id: "A", label: "Go" }] } }))).toBe(false);
    expect(
      isBulkEligible(item("1", { decision: { options: [{ id: "A", label: "Go" }], recommended: "Z" } })),
    ).toBe(false);
    expect(isBulkEligible(item("1", { decision: null }))).toBe(false);
  });
});

describe("batch builder", () => {
  const items = [item("1"), item("2", { urgency: 3 }), item("3", { decision: { options: [], recommended: "A" } })];

  it("lists only eligible items", () => {
    expect(eligibleItems(items).map((entry) => entry.id)).toEqual(["1"]);
  });

  it("builds one approve per selected eligible item with its recommended option", () => {
    const batch = buildBulkBatch(
      [item("1"), item("4", { decision: { options: [{ id: "X", label: "x" }, { id: "Y", label: "y" }], recommended: "Y" } })],
      new Set(["1", "4"]),
    );
    expect(batch).toEqual([
      { itemId: "1", option: "A" },
      { itemId: "4", option: "Y" },
    ]);
  });

  it("ignores selected ids that are ineligible or missing", () => {
    expect(buildBulkBatch(items, new Set(["2", "3", "99"]))).toEqual([]);
  });
});
