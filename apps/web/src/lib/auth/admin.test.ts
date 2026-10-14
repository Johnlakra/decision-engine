import { describe, expect, it } from "vitest";
import { canProxy, isAdminEmail } from "./admin";
import { parseAllowList } from "./allow-list";

describe("isAdminEmail", () => {
  const admins = parseAllowList("Boss@Example.com, other@example.com");

  it("accepts a listed email regardless of case", () => {
    expect(isAdminEmail("boss@example.com", admins)).toBe(true);
  });

  it("refuses unlisted, missing and empty-list cases (fail closed)", () => {
    expect(isAdminEmail("user@example.com", admins)).toBe(false);
    expect(isAdminEmail(null, admins)).toBe(false);
    expect(isAdminEmail("boss@example.com", parseAllowList(""))).toBe(false);
    expect(isAdminEmail("boss@example.com", parseAllowList(undefined))).toBe(false);
  });
});

describe("canProxy", () => {
  const admins = parseAllowList("boss@example.com");

  it("lets only admins write settings", () => {
    expect(canProxy("PUT", ["settings"], "user@example.com", admins)).toBe(false);
    expect(canProxy("PUT", ["settings"], "boss@example.com", admins)).toBe(true);
  });

  it("lets only admins write niches", () => {
    expect(canProxy("PUT", ["niches", "inbox"], "user@example.com", admins)).toBe(false);
    expect(canProxy("PUT", ["niches", "inbox"], "boss@example.com", admins)).toBe(true);
    expect(canProxy("GET", ["niches", "inbox"], "user@example.com", admins)).toBe(true);
  });

  it("lets only admins create and patch sources", () => {
    expect(canProxy("POST", ["sources"], "user@example.com", admins)).toBe(false);
    expect(canProxy("PATCH", ["sources", "x"], "user@example.com", admins)).toBe(false);
    expect(canProxy("PATCH", ["sources", "x"], "boss@example.com", admins)).toBe(true);
    expect(canProxy("GET", ["sources"], "user@example.com", admins)).toBe(true);
    expect(canProxy("GET", ["stats", "today"], "user@example.com", admins)).toBe(true);
  });

  it("leaves reads and other writes to every signed-in user", () => {
    expect(canProxy("GET", ["settings"], "user@example.com", admins)).toBe(true);
    expect(canProxy("POST", ["items", "x", "decision"], "user@example.com", admins)).toBe(true);
  });
});
