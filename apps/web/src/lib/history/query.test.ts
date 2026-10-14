import { describe, expect, it } from "vitest";
import { HISTORY_PAGE_SIZE, historyPath } from "./query";

const EMPTY = { niche: "", source: "", q: "" };

describe("historyPath", () => {
  it("sends only the page size when there are no filters or cursor", () => {
    expect(historyPath(EMPTY, null)).toBe(`/items?limit=${HISTORY_PAGE_SIZE}`);
  });

  it("includes trimmed filters and skips blank ones", () => {
    const path = historyPath({ niche: " inbox ", source: "   ", q: " free credits " }, null);

    const params = new URLSearchParams(path.split("?")[1]);
    expect(params.get("niche")).toBe("inbox");
    expect(params.has("source")).toBe(false);
    expect(params.get("q")).toBe("free credits");
    expect(params.get("limit")).toBe(String(HISTORY_PAGE_SIZE));
  });

  it("adds the cursor when given", () => {
    const params = new URLSearchParams(historyPath(EMPTY, "abc==").split("?")[1]);

    expect(params.get("cursor")).toBe("abc==");
  });

  it("only emits parameters the proxy allows", () => {
    const path = historyPath({ niche: "a", source: "b", q: "c" }, "d");

    const names = [...new URLSearchParams(path.split("?")[1]).keys()];
    expect(names.sort()).toEqual(["cursor", "limit", "niche", "q", "source"]);
  });
});
