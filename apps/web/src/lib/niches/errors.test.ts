import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/request";
import { saveErrorView } from "./errors";

describe("saveErrorView", () => {
  it("flags 403 as admin only", () => {
    expect(saveErrorView(new ApiError(403))).toEqual({ kind: "admin", fields: {}, general: [] });
  });

  it("maps 422 pointers to fields and keeps the rest as general errors", () => {
    const error = new ApiError(422, [
      { json_pointer: "/autonomy", message: "'yolo' is not one of ['suggest', 'ask', 'auto']" },
      { json_pointer: "/actions/2", message: "unknown action" },
      { json_pointer: "/prompt", message: "too short" },
      { json_pointer: "", message: "not an object" },
    ]);

    expect(saveErrorView(error)).toEqual({
      kind: "validation",
      fields: {
        autonomy: ["'yolo' is not one of ['suggest', 'ask', 'auto']"],
        actions: ["unknown action"],
      },
      general: [
        { pointer: "/prompt", message: "too short" },
        { pointer: "", message: "not an object" },
      ],
      all: [
        { pointer: "/autonomy", message: "'yolo' is not one of ['suggest', 'ask', 'auto']" },
        { pointer: "/actions/2", message: "unknown action" },
        { pointer: "/prompt", message: "too short" },
        { pointer: "", message: "not an object" },
      ],
    });
  });

  it("ignores malformed error entries", () => {
    const view = saveErrorView(new ApiError(422, [null, { message: 3 }, "x"]));
    expect(view).toEqual({ kind: "validation", fields: {}, general: [], all: [] });
  });

  it("treats other failures as generic", () => {
    expect(saveErrorView(new ApiError(500)).kind).toBe("other");
    expect(saveErrorView(new TypeError("network")).kind).toBe("other");
  });
});
