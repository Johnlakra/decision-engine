"use client";

import type { GeneralError } from "@/lib/niches/errors";
import { translate, type Locale } from "@/lib/i18n";
import type { YamlParseResult } from "@/lib/niches/yaml";

interface NicheYamlTabProps {
  readonly text: string;
  readonly syntax: YamlParseResult;
  readonly serverErrors: readonly GeneralError[];
  readonly locale: Locale;
  readonly onChange: (text: string) => void;
}

/** The YAML text. Syntax errors are client-side only; server errors are listed above the editor. */
export function NicheYamlTab({ text, syntax, serverErrors, locale, onChange }: NicheYamlTabProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const syntaxMessage = syntax.ok
    ? null
    : syntax.reason === "not_mapping"
      ? t("niches.yaml.notMapping")
      : t("niches.yaml.syntax", { line: syntax.line, column: syntax.column, message: syntax.message });

  return (
    <div className="space-y-2">
      {serverErrors.length > 0 ? (
        <ul id="yaml-server-errors" className="list-disc pl-5 text-[13px] text-danger">
          {serverErrors.map((error) => (
            <li key={`${error.pointer}:${error.message}`}>
              <code>{error.pointer === "" ? t("niches.errors.root") : error.pointer}</code> {error.message}
            </li>
          ))}
        </ul>
      ) : null}
      <label className="block text-[13px] font-medium" htmlFor="niche-yaml">
        {t("niches.yaml.label")}
      </label>
      <textarea
        id="niche-yaml"
        spellCheck={false}
        rows={24}
        className="w-full rounded-[8px] border border-border bg-surface p-2 font-mono text-[13px]"
        value={text}
        aria-invalid={syntaxMessage !== null || undefined}
        aria-describedby="niche-yaml-status"
        onChange={(e) => onChange(e.target.value)}
      />
      <p id="niche-yaml-status" role={syntaxMessage ? "alert" : "status"} className={syntaxMessage ? "text-[13px] text-danger" : "text-[13px] text-muted"}>
        {syntaxMessage ?? `${t("niches.yaml.ok")} ${t("niches.yaml.hint")}`}
      </p>
    </div>
  );
}
