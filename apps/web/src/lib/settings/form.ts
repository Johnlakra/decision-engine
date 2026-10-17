import type { components } from "@decision-engine/client";

/**
 * Settings form <-> API payload. Pure. The payload type is the generated `SettingsIn`, so the
 * form cannot send a shape the API refuses. Checks here only catch mistakes early; the API
 * still validates everything.
 */

export type SettingsPayload = components["schemas"]["SettingsIn"];
export type Language = SettingsPayload["languages"][number];

export const MAX_INTERESTS = 20;
export const MAX_INTEREST_CHARS = 60;
export const MAX_PING_CAP = 50;

/** "env" = no stored mode, so the server's LAYA_MODE applies. "on" is refused by the API, so it is not offered. */
export type LayaChoice = "env" | "off" | "shadow";

export interface SettingsForm {
  readonly quietFrom: string;
  readonly quietTo: string;
  readonly digestHour: string;
  readonly pingCap: string;
  readonly interests: string;
  readonly languages: readonly Language[];
  readonly layaMode: LayaChoice;
}

export type SettingsField = "quiet" | "digestHour" | "pingCap" | "interests" | "languages";

export type SettingsFormResult =
  | { readonly ok: true; readonly payload: SettingsPayload }
  | { readonly ok: false; readonly errors: readonly SettingsField[] };

const HOUR_PATTERN = /^\d{1,2}$/;
const COUNT_PATTERN = /^\d{1,3}$/;

function hourOf(value: string): number | null {
  if (!HOUR_PATTERN.test(value)) {
    return null;
  }
  const hour = Number(value);
  return hour >= 0 && hour <= 23 ? hour : null;
}

function countOf(value: string, max: number): number | null {
  if (!COUNT_PATTERN.test(value)) {
    return null;
  }
  const count = Number(value);
  return count <= max ? count : null;
}

/** Comma-separated text -> trimmed, non-empty interests. Null when a rule is broken. */
export function parseInterests(text: string): string[] | null {
  const items = text
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item !== "");
  const withinLength = items.every((item) => item.length <= MAX_INTEREST_CHARS);
  return withinLength && items.length <= MAX_INTERESTS ? items : null;
}

export function formToPayload(form: SettingsForm): SettingsFormResult {
  const from = hourOf(form.quietFrom);
  const to = hourOf(form.quietTo);
  const digest = hourOf(form.digestHour);
  const cap = countOf(form.pingCap, MAX_PING_CAP);
  const interests = parseInterests(form.interests);
  const errors: SettingsField[] = [];
  if (from === null || to === null) {
    errors.push("quiet");
  }
  if (digest === null) {
    errors.push("digestHour");
  }
  if (cap === null) {
    errors.push("pingCap");
  }
  if (interests === null) {
    errors.push("interests");
  }
  if (form.languages.length === 0) {
    errors.push("languages");
  }
  if (errors.length > 0 || from === null || to === null || digest === null || cap === null || interests === null) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    payload: {
      quiet_hours: [from, to],
      digest_hour: digest,
      ping_cap_per_day: cap,
      interests,
      languages: [...form.languages],
      laya_mode: form.layaMode === "env" ? null : form.layaMode,
    },
  };
}

export function formFromSettings(settings: SettingsPayload): SettingsForm {
  return {
    quietFrom: String(settings.quiet_hours[0] ?? 22),
    quietTo: String(settings.quiet_hours[1] ?? 7),
    digestHour: String(settings.digest_hour),
    pingCap: String(settings.ping_cap_per_day),
    interests: settings.interests.join(", "),
    languages: settings.languages,
    layaMode: toLayaChoice(settings.laya_mode),
  };
}

function toLayaChoice(stored: SettingsPayload["laya_mode"]): LayaChoice {
  return stored === "off" || stored === "shadow" ? stored : "env";
}
