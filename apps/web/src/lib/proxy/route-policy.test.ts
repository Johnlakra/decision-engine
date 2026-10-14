import { describe, expect, it } from "vitest";
import { listSearch, planProxy } from "./route-policy";

const ITEM_ID = "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e";
const NONE = new URLSearchParams();

describe("planProxy", () => {
  it("lists items and passes only known filters through", () => {
    const params = new URLSearchParams("status=awaiting_approval&niche=generic&evil=1&limit=500");

    const plan = planProxy("GET", ["items"], params);

    expect(plan).toEqual({
      ok: true,
      method: "GET",
      path: "/v1/items",
      search: "?status=awaiting_approval&niche=generic&limit=100",
    });
  });

  it("reads one item and posts a decision for a valid id", () => {
    expect(planProxy("GET", ["items", ITEM_ID], NONE)).toMatchObject({
      ok: true,
      path: `/v1/items/${ITEM_ID}`,
    });
    expect(planProxy("POST", ["items", ITEM_ID, "decision"], NONE)).toMatchObject({
      ok: true,
      method: "POST",
      path: `/v1/items/${ITEM_ID}/decision`,
    });
  });

  it("refuses unknown resources, bad ids and extra segments", () => {
    expect(planProxy("GET", ["tenants"], NONE)).toEqual({ ok: false, status: 404 });
    expect(planProxy("GET", ["items", "../../secrets"], NONE)).toEqual({ ok: false, status: 404 });
    expect(planProxy("GET", ["items", ITEM_ID, "decision", "x"], NONE)).toEqual({
      ok: false,
      status: 404,
    });
  });

  it("answers 405 for a known path with the wrong method", () => {
    expect(planProxy("DELETE", ["items"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("GET", ["items", ITEM_ID, "decision"], NONE)).toEqual({
      ok: false,
      status: 405,
    });
  });
});

describe("planProxy settings and activity", () => {
  it("allows GET and PUT on /settings with the method preserved and no query", () => {
    const params = new URLSearchParams("evil=1");
    expect(planProxy("GET", ["settings"], params)).toEqual({
      ok: true,
      method: "GET",
      path: "/v1/settings",
      search: "",
    });
    expect(planProxy("PUT", ["settings"], params)).toEqual({
      ok: true,
      method: "PUT",
      path: "/v1/settings",
      search: "",
    });
  });

  it("answers 405 for other methods on /settings and 404 for sub-paths", () => {
    for (const method of ["POST", "DELETE", "PATCH"]) {
      expect(planProxy(method, ["settings"], NONE)).toEqual({ ok: false, status: 405 });
    }
    expect(planProxy("GET", ["settings", "x"], NONE)).toEqual({ ok: false, status: 404 });
  });

  it("allows GET only on an item's activity", () => {
    expect(planProxy("GET", ["items", ITEM_ID, "activity"], NONE)).toEqual({
      ok: true,
      method: "GET",
      path: `/v1/items/${ITEM_ID}/activity`,
      search: "",
    });
    expect(planProxy("POST", ["items", ITEM_ID, "activity"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("GET", ["items", "nope", "activity"], NONE)).toEqual({ ok: false, status: 404 });
  });

  it("allows POST only on decision and refuses PUT on items", () => {
    expect(planProxy("PUT", ["items", ITEM_ID, "decision"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("PUT", ["items", ITEM_ID], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("GET", ["items", ITEM_ID, "other"], NONE)).toEqual({ ok: false, status: 404 });
  });
});

describe("planProxy niches", () => {
  it("allows GET on the list and drops any query", () => {
    expect(planProxy("GET", ["niches"], new URLSearchParams("evil=1"))).toEqual({
      ok: true,
      method: "GET",
      path: "/v1/niches",
      search: "",
    });
  });

  it("allows GET and PUT on one niche by slug", () => {
    expect(planProxy("GET", ["niches", "inbox"], NONE)).toEqual({
      ok: true,
      method: "GET",
      path: "/v1/niches/inbox",
      search: "",
    });
    expect(planProxy("PUT", ["niches", "news_radar"], NONE)).toEqual({
      ok: true,
      method: "PUT",
      path: "/v1/niches/news_radar",
      search: "",
    });
  });

  it("refuses names that are not lowercase slugs", () => {
    for (const name of ["Inbox", "1inbox", "a", "../x", "in-box", "a".repeat(41), "in box"]) {
      expect(planProxy("GET", ["niches", name], NONE)).toEqual({ ok: false, status: 404 });
    }
  });

  it("never reaches the reload route", () => {
    expect(planProxy("POST", ["niches", "reload"], NONE)).toEqual({ ok: false, status: 404 });
    expect(planProxy("PUT", ["niches", "reload"], NONE)).toEqual({ ok: false, status: 404 });
  });

  it("answers 405 for other methods and 404 for sub-paths", () => {
    expect(planProxy("POST", ["niches"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("PUT", ["niches"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("DELETE", ["niches", "inbox"], NONE)).toEqual({ ok: false, status: 405 });
    expect(planProxy("GET", ["niches", "inbox", "x"], NONE)).toEqual({ ok: false, status: 404 });
  });
});

describe("listSearch", () => {
  it("drops empty values and clamps a bad limit to one", () => {
    expect(listSearch(new URLSearchParams("status=&limit=abc"))).toBe("?limit=1");
  });

  it("is empty when no filter is given", () => {
    expect(listSearch(NONE)).toBe("");
  });
});
