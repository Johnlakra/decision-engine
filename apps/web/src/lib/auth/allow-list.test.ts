import { describe, expect, it } from "vitest";
import { isAllowedEmail, parseAllowList } from "./allow-list";

describe("parseAllowList", () => {
  it("splits, trims and lowercases the configured emails", () => {
    const allowed = parseAllowList(" Owner@Example.com , second@example.com ");

    expect([...allowed]).toEqual(["owner@example.com", "second@example.com"]);
  });

  it("is empty when the variable is unset, so nobody is admitted", () => {
    expect(parseAllowList(undefined).size).toBe(0);
    expect(parseAllowList("  ,  ").size).toBe(0);
  });
});

describe("isAllowedEmail", () => {
  const allowed = parseAllowList("owner@example.com");

  it("admits a listed account regardless of case", () => {
    expect(isAllowedEmail("OWNER@example.com", allowed)).toBe(true);
  });

  it("refuses unlisted, missing and blank addresses", () => {
    expect(isAllowedEmail("someone@example.com", allowed)).toBe(false);
    expect(isAllowedEmail(null, allowed)).toBe(false);
    expect(isAllowedEmail("", parseAllowList(""))).toBe(false);
  });
});
