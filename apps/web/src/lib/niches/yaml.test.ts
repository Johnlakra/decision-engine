import { describe, expect, it } from "vitest";
import { parseNicheYaml, stringifyNiche } from "./yaml";

describe("parseNicheYaml", () => {
  it("parses a mapping", () => {
    expect(parseNicheYaml("name: inbox\nautonomy: ask\n")).toEqual({
      ok: true,
      value: { name: "inbox", autonomy: "ask" },
    });
  });

  it("reads yes and no as booleans, like the server (YAML 1.1)", () => {
    expect(parseNicheYaml("enabled: yes\nnotify:\n  digest: no\n")).toEqual({
      ok: true,
      value: { enabled: true, notify: { digest: false } },
    });
  });

  it("reports a duplicate key with its line", () => {
    const result = parseNicheYaml("name: a\nname: b\n");
    expect(result).toMatchObject({ ok: false, line: 2 });
  });

  it("reports a syntax error with line and column", () => {
    const result = parseNicheYaml("name: a\nactions: [one, two\n");
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.line).toBeGreaterThanOrEqual(1);
      expect(result.column).toBeGreaterThanOrEqual(1);
      expect(result.message).not.toBe("");
    }
  });

  it("refuses a top level that is not a mapping", () => {
    expect(parseNicheYaml("- a\n- b\n")).toMatchObject({ ok: false, reason: "not_mapping" });
    expect(parseNicheYaml("")).toMatchObject({ ok: false, reason: "not_mapping" });
    expect(parseNicheYaml("just text")).toMatchObject({ ok: false, reason: "not_mapping" });
  });

  it("refuses alias bombs", () => {
    const anchors = Array.from({ length: 60 }, (_, i) => `- *a`).join("\n");
    const result = parseNicheYaml(`base: &a [1, 2]\nlist:\n${anchors}\n`);
    expect(result.ok).toBe(false);
  });
});

describe("stringifyNiche", () => {
  it("round-trips a config", () => {
    const config = { name: "inbox", actions: ["archive"], notify: { digest: true } };
    expect(parseNicheYaml(stringifyNiche(config))).toEqual({ ok: true, value: config });
  });
});

describe("stringifyNiche quoting", () => {
  it("keeps the string 'yes' a string after a round trip", () => {
    const config = { options_hint: ["yes", "no"] };
    expect(parseNicheYaml(stringifyNiche(config))).toEqual({ ok: true, value: config });
  });
});
