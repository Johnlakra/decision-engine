import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/request";
import { buildSourceBody, slugFromName, sortSources, sourceErrorView, validateSource } from "./form";

const VALID = { type: "rss", name: "Example", slug: "example-feed", value: "https://example.com/feed.xml" } as const;

describe("validateSource", () => {
  it("accepts a valid rss feed", () => {
    expect(validateSource(VALID)).toEqual({});
  });

  it("enforces the API limits", () => {
    const errors = validateSource({
      type: "rss",
      name: "x".repeat(121),
      slug: "A",
      value: "http://example.com/feed",
    });

    expect(Object.keys(errors).sort()).toEqual(["name", "slug", "value"]);
  });

  it("requires a name, and caps a google_news query at 200 characters", () => {
    expect(validateSource({ ...VALID, name: " " }).name).toBeDefined();
    const news = { ...VALID, type: "google_news" } as const;
    expect(validateSource({ ...news, value: "punjab rice" })).toEqual({});
    expect(validateSource({ ...news, value: "q".repeat(201) }).value).toBeDefined();
    expect(validateSource({ ...news, value: "" }).value).toBeDefined();
  });

  it("caps urls at 2048 characters", () => {
    expect(validateSource({ ...VALID, value: `https://a.com/${"x".repeat(2048)}` }).value).toBeDefined();
  });
});

describe("buildSourceBody", () => {
  it("sends url for rss and query for google_news, trimmed", () => {
    expect(buildSourceBody({ ...VALID, name: " Example ", value: " https://example.com/f " })).toEqual({
      type: "rss",
      name: "Example",
      slug: "example-feed",
      config: { url: "https://example.com/f" },
    });
    expect(buildSourceBody({ ...VALID, type: "google_news", value: "punjab rice" }).config).toEqual({
      query: "punjab rice",
    });
  });
});

describe("slugFromName", () => {
  it("makes a slug that matches the API pattern", () => {
    expect(slugFromName("Punjab Rice News!")).toBe("punjab-rice-news");
    expect(slugFromName("  9 lives ")).toBe("lives");
  });
});

describe("sortSources", () => {
  it("sorts by name without changing the input", () => {
    const rows = [{ name: "b" }, { name: "A" }, { name: "c" }];

    expect(sortSources(rows).map((row) => row.name)).toEqual(["A", "b", "c"]);
    expect(rows[0]?.name).toBe("b");
  });
});

describe("sourceErrorView", () => {
  it("maps 409 to a taken slug", () => {
    expect(sourceErrorView(new ApiError(409))).toEqual({ kind: "slugTaken", fields: {}, general: [] });
  });

  it("maps 422 field errors next to fields and the rest to general", () => {
    const view = sourceErrorView(
      new ApiError(422, [
        { field: "body.slug", message: "bad slug", code: "string_pattern_mismatch" },
        { field: "body.config", message: "config.url must be https", code: "value_error" },
        { field: "body", message: "other", code: "value_error" },
      ]),
    );

    expect(view).toEqual({
      kind: "validation",
      fields: { slug: ["bad slug"], value: ["config.url must be https"] },
      general: ["other"],
    });
  });

  it("maps 403 to admin and anything else to other", () => {
    expect(sourceErrorView(new ApiError(403)).kind).toBe("admin");
    expect(sourceErrorView(new Error("x")).kind).toBe("other");
  });
});
