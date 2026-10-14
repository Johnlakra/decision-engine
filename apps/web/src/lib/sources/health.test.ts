import { describe, expect, it } from "vitest";
import { sourceHealth } from "./health";

describe("sourceHealth", () => {
  it("is paused when disabled, whatever the errors", () => {
    expect(sourceHealth({ enabled: false, error_count: 5 })).toBe("paused");
  });

  it("is ok with no errors, failing with some", () => {
    expect(sourceHealth({ enabled: true, error_count: 0 })).toBe("ok");
    expect(sourceHealth({ enabled: true, error_count: 3 })).toBe("failing");
  });
});
