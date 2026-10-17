import { describe, expect, it } from "vitest";
import type { ItemOut } from "@/lib/api/items";
import { applyFilters, filterChoices, filterFromParams, NO_FILTER, paramsWithFilter } from "./filters";

function item(id: string, niche: string | null, source: string): ItemOut {
  return {
    id,
    tenant_id: "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d00",
    source,
    source_ref: id,
    sensitivity: "normal",
    status: "awaiting_approval",
    niche,
    created_at: "2026-10-01T00:00:00Z",
    received_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
  };
}

const ITEMS = [
  item("a", "news_radar", "rss"),
  item("b", "tech_stack", "webhook"),
  item("c", "news_radar", "webhook"),
  item("d", null, "rss"),
];

describe("filterChoices", () => {
  it("lists distinct niches and sources, sorted, without empty values", () => {
    expect(filterChoices(ITEMS)).toEqual({
      niches: ["news_radar", "tech_stack"],
      sources: ["rss", "webhook"],
    });
  });
});

describe("applyFilters", () => {
  it("returns every item when no chip is active", () => {
    expect(applyFilters(ITEMS, NO_FILTER)).toHaveLength(4);
  });

  it("keeps items that match both the niche and the source chip", () => {
    const filtered = applyFilters(ITEMS, { niche: "news_radar", source: "webhook" });

    expect(filtered.map((entry) => entry.id)).toEqual(["c"]);
  });

  it("drops items with no niche once a niche chip is active", () => {
    expect(applyFilters(ITEMS, { niche: "news_radar", source: null }).map((entry) => entry.id)).toEqual(["a", "c"]);
  });
});

describe("URL search params", () => {
  it("reads the niche and source chips from the query string", () => {
    expect(filterFromParams(new URLSearchParams("niche=tech_stack&source=webhook"))).toEqual({
      niche: "tech_stack",
      source: "webhook",
    });
    expect(filterFromParams(new URLSearchParams("niche=&other=1"))).toEqual(NO_FILTER);
  });

  it("writes the chips and keeps unrelated params, without mutating the input", () => {
    const input = new URLSearchParams("limit=5&niche=old");

    const next = paramsWithFilter(input, { niche: null, source: "rss" });

    expect(next.toString()).toBe("limit=5&source=rss");
    expect(input.toString()).toBe("limit=5&niche=old");
  });
});
