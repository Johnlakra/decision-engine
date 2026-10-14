import { describe, expect, it } from "vitest";
import { confidenceLabel } from "./confidence";
import { queueActionForKey } from "./keys";
import { UNDO_WINDOW_MS, cancelDecision, dueDecisions, scheduleDecision } from "./undo";

describe("queueActionForKey", () => {
  it("maps the documented keys to actions", () => {
    expect(queueActionForKey("a")).toEqual({ type: "approve" });
    expect(queueActionForKey("r")).toEqual({ type: "reject" });
    expect(queueActionForKey("j")).toEqual({ type: "next" });
    expect(queueActionForKey("k")).toEqual({ type: "previous" });
    expect(queueActionForKey("?")).toEqual({ type: "help" });
  });

  it("maps 1 to 5 to zero-based option indexes", () => {
    expect(queueActionForKey("1")).toEqual({ type: "choose", index: 0 });
    expect(queueActionForKey("5")).toEqual({ type: "choose", index: 4 });
  });

  it("ignores keys outside the map, including prototype names", () => {
    expect(queueActionForKey("6")).toBeNull();
    expect(queueActionForKey("Shift")).toBeNull();
    expect(queueActionForKey("constructor")).toBeNull();
  });
});

describe("confidenceLabel", () => {
  it("uses words at the documented thresholds", () => {
    expect(confidenceLabel(0.8)).toBe("high");
    expect(confidenceLabel(0.79)).toBe("medium");
    expect(confidenceLabel(0.5)).toBe("medium");
    expect(confidenceLabel(0.49)).toBe("low");
  });

  it("returns null when there is no score", () => {
    expect(confidenceLabel(null)).toBeNull();
    expect(confidenceLabel(undefined)).toBeNull();
    expect(confidenceLabel(Number.NaN)).toBeNull();
  });
});

describe("undo window", () => {
  it("holds a decision until the window closes, then releases it", () => {
    const pending = scheduleDecision([], "item-1", "approve", 1_000);

    expect(dueDecisions(pending, 1_000 + UNDO_WINDOW_MS - 1)).toEqual([]);
    expect(dueDecisions(pending, 1_000 + UNDO_WINDOW_MS)).toHaveLength(1);
  });

  it("undo removes the held decision without touching the others", () => {
    const first = scheduleDecision([], "item-1", "approve", 0);
    const both = scheduleDecision(first, "item-2", "reject", 0);

    const undone = cancelDecision(both, "item-1");

    expect(undone.map((entry) => entry.itemId)).toEqual(["item-2"]);
    expect(both).toHaveLength(2); // the input list is not mutated
  });

  it("a second action on the same item replaces the first", () => {
    const first = scheduleDecision([], "item-1", "approve", 0);

    const replaced = scheduleDecision(first, "item-1", "reject", 5);

    expect(replaced).toHaveLength(1);
    expect(replaced[0]?.verdict).toBe("reject");
  });
});
