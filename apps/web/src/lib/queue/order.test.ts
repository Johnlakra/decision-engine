import { describe, expect, it } from "vitest";
import type { ItemOut } from "@/lib/api/items";
import { sortQueue } from "./order";

function item(overrides: Partial<ItemOut>): ItemOut {
  return {
    id: overrides.id ?? "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",
    tenant_id: "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d00",
    source: "rss",
    source_ref: "ref",
    sensitivity: "normal",
    status: "awaiting_approval",
    created_at: "2026-10-01T00:00:00Z",
    received_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

describe("sortQueue", () => {
  it("puts higher urgency first", () => {
    const sorted = sortQueue([item({ id: "low", urgency: 1 }), item({ id: "high", urgency: 3 })]);

    expect(sorted.map((entry) => entry.id)).toEqual(["high", "low"]);
  });

  it("breaks urgency ties by the earlier deadline, with no deadline last", () => {
    const sorted = sortQueue([
      item({ id: "none", urgency: 2 }),
      item({ id: "late", urgency: 2, deadline_at: "2026-10-20T00:00:00Z" }),
      item({ id: "soon", urgency: 2, deadline_at: "2026-10-10T00:00:00Z" }),
    ]);

    expect(sorted.map((entry) => entry.id)).toEqual(["soon", "late", "none"]);
  });

  it("breaks remaining ties by the oldest created_at first", () => {
    const sorted = sortQueue([
      item({ id: "newer", created_at: "2026-10-05T00:00:00Z" }),
      item({ id: "older", created_at: "2026-10-02T00:00:00Z" }),
    ]);

    expect(sorted.map((entry) => entry.id)).toEqual(["older", "newer"]);
  });

  it("treats a missing urgency as the lowest and does not mutate the input", () => {
    const input = [item({ id: "unset" }), item({ id: "set", urgency: 1 })];
    const before = input.map((entry) => entry.id);

    const sorted = sortQueue(input);

    expect(sorted.map((entry) => entry.id)).toEqual(["set", "unset"]);
    expect(input.map((entry) => entry.id)).toEqual(before);
  });
});
