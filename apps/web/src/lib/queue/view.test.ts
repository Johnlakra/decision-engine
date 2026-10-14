import { describe, expect, it } from "vitest";
import { confidenceOf, moveIndex, optionsOf, orderedOptions, rationaleOf } from "./view";

const decision = {
  options: [
    { id: "A", label: "Save and act", actions: [] },
    { id: "B", label: "Read later" },
    { id: "C", label: "Not interested" },
  ],
  recommended: "B",
  rationale: "Matches your interests.",
  confidence: 0.9,
};

describe("optionsOf", () => {
  it("keeps only well-formed options", () => {
    const messy = { options: [{ id: "A", label: "ok" }, { id: 7, label: "bad" }, null, "x"] };

    expect(optionsOf(messy)).toEqual([{ id: "A", label: "ok" }]);
  });

  it("is empty when there is no decision yet", () => {
    expect(optionsOf(null)).toEqual([]);
    expect(optionsOf({ options: "nope" })).toEqual([]);
  });
});

describe("orderedOptions", () => {
  it("puts the recommended option first and keeps the rest in order", () => {
    expect(orderedOptions(decision).map((option) => option.id)).toEqual(["B", "A", "C"]);
  });
});

describe("rationaleOf and confidenceOf", () => {
  it("returns the rationale only when it has text", () => {
    expect(rationaleOf(decision)).toBe("Matches your interests.");
    expect(rationaleOf({ rationale: "   " })).toBeNull();
  });

  it("accepts confidence only within 0 to 1", () => {
    expect(confidenceOf(decision)).toBe(0.9);
    expect(confidenceOf({ confidence: 1.5 })).toBeNull();
    expect(confidenceOf({ confidence: "high" })).toBeNull();
  });
});

describe("moveIndex", () => {
  it("stops at both ends instead of wrapping", () => {
    expect(moveIndex(0, -1, 3)).toBe(0);
    expect(moveIndex(2, 1, 3)).toBe(2);
    expect(moveIndex(0, 1, 3)).toBe(1);
  });

  it("returns zero for an empty queue", () => {
    expect(moveIndex(4, 1, 0)).toBe(0);
  });
});
