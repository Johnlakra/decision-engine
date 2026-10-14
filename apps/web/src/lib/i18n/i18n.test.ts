import { describe, expect, it } from "vitest";
import { resolveLocale, translate } from "./index";

describe("resolveLocale", () => {
  it("keeps supported locales and falls back to English for anything else", () => {
    expect(resolveLocale("pa")).toBe("pa");
    expect(resolveLocale("fr")).toBe("en");
    expect(resolveLocale(null)).toBe("en");
  });
});

describe("translate", () => {
  it("returns the message for the requested locale", () => {
    expect(translate("hi", "queue.retry")).toBe("फिर से कोशिश करें");
  });

  it("falls back to English when a locale lacks a key, then to the key itself", () => {
    expect(translate("pa", "app.name")).toBe("ਡਿਸੀਜ਼ਨ ਇੰਜਣ");
    expect(translate("en", "missing.key")).toBe("missing.key");
  });

  it("substitutes named placeholders and leaves unknown ones visible", () => {
    expect(translate("en", "queue.count", { count: 12 })).toBe("12 to decide");
    expect(translate("en", "queue.count")).toBe("{count} to decide");
  });
});
