import { parse, stringify, YAMLParseError } from "yaml";

/**
 * Client-side YAML check (ADR 0011): syntax only. YAML 1.1 matches the server's PyYAML, so `yes`
 * means the same on both sides. Schema and semantic errors come back from the PUT.
 */

export type NicheConfig = Record<string, unknown>;

export const YAML_OPTIONS = { version: "1.1", uniqueKeys: true, maxAliasCount: 50 } as const;

export type YamlParseResult =
  | { readonly ok: true; readonly value: NicheConfig }
  | {
      readonly ok: false;
      readonly reason: "syntax" | "not_mapping";
      readonly message: string;
      readonly line: number;
      readonly column: number;
    };

function isMapping(value: unknown): value is NicheConfig {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseNicheYaml(text: string): YamlParseResult {
  try {
    const value: unknown = parse(text, YAML_OPTIONS);
    if (isMapping(value)) {
      return { ok: true, value };
    }
    return { ok: false, reason: "not_mapping", message: "", line: 1, column: 1 };
  } catch (error) {
    if (error instanceof YAMLParseError) {
      const position = error.linePos?.[0];
      return {
        ok: false,
        reason: "syntax",
        message: error.message.split("\n")[0] ?? error.message,
        line: position?.line ?? 1,
        column: position?.col ?? 1,
      };
    }
    // Alias limit and other non-parse failures still mean "not usable YAML".
    const message = error instanceof Error ? error.message : "Invalid YAML";
    return { ok: false, reason: "syntax", message, line: 1, column: 1 };
  }
}

export function stringifyNiche(config: NicheConfig): string {
  return stringify(config, { version: "1.1" });
}
