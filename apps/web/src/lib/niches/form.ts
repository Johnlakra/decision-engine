import type { NicheConfig } from "./yaml";

/**
 * Basic-form view of a niche config. The config object is the single source of truth (the YAML tab
 * edits the same object), so a field change copies the config and touches only its own keys.
 */

export type Autonomy = "suggest" | "ask" | "auto";
export const AUTONOMY_VALUES: readonly Autonomy[] = ["suggest", "ask", "auto"];
export const URGENCY_VALUES = ["0", "1", "2"] as const;

export interface NicheForm {
  readonly label: string;
  readonly description: string;
  readonly autonomy: string;
  readonly actions: string;
  readonly autoActions: string;
  readonly urgentPing: boolean;
  readonly digest: boolean;
  readonly minUrgencyForPing: string;
}

export type FormField = keyof NicheForm;

const NOTIFY_KEYS = { urgentPing: "urgent_ping", digest: "digest" } as const;

const DEFAULT_MIN_URGENCY = "2";

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function lines(value: unknown): string {
  return Array.isArray(value) ? value.filter((entry) => typeof entry === "string").join("\n") : "";
}

function notifyOf(config: NicheConfig): Record<string, unknown> {
  const notify = config.notify;
  return typeof notify === "object" && notify !== null && !Array.isArray(notify)
    ? (notify as Record<string, unknown>)
    : {};
}

export function formFromConfig(config: NicheConfig): NicheForm {
  const notify = notifyOf(config);
  const urgency = notify.min_urgency_for_ping;
  return {
    label: text(config.label),
    description: text(config.description),
    autonomy: text(config.autonomy) || "ask",
    actions: lines(config.actions),
    autoActions: lines(config.auto_actions),
    urgentPing: typeof notify.urgent_ping === "boolean" ? notify.urgent_ping : true,
    digest: typeof notify.digest === "boolean" ? notify.digest : true,
    minUrgencyForPing: typeof urgency === "number" ? String(urgency) : DEFAULT_MIN_URGENCY,
  };
}

export function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

function urgencyValue(value: string): number | string {
  return /^\d+$/.test(value) ? Number(value) : value;
}

/** Returns a new config with one form field applied. Other keys are kept as they are. */
export function applyFormField(config: NicheConfig, field: FormField, value: string | boolean): NicheConfig {
  switch (field) {
    case "label":
    case "description":
    case "autonomy":
      return { ...config, [field]: value };
    case "actions":
      return { ...config, actions: parseLines(String(value)) };
    case "autoActions":
      return { ...config, auto_actions: parseLines(String(value)) };
    case "minUrgencyForPing":
      return { ...config, notify: { ...notifyOf(config), min_urgency_for_ping: urgencyValue(String(value)) } };
    case "urgentPing":
    case "digest":
      return { ...config, notify: { ...notifyOf(config), [NOTIFY_KEYS[field]]: value === true } };
  }
}

const TOP_LEVEL: Readonly<Record<string, FormField>> = {
  label: "label",
  description: "description",
  autonomy: "autonomy",
  actions: "actions",
  auto_actions: "autoActions",
};
const NOTIFY_FIELDS: Readonly<Record<string, FormField>> = {
  urgent_ping: "urgentPing",
  digest: "digest",
  min_urgency_for_ping: "minUrgencyForPing",
};

/** JSON pointer (`/autonomy`, `/actions/2`, `/notify/digest`) -> the form field it names, or null. */
export function pointerField(pointer: string): FormField | null {
  const [, first, second] = pointer.split("/");
  if (first === undefined) {
    return null;
  }
  if (first === "notify") {
    return second === undefined ? null : (NOTIFY_FIELDS[second] ?? null);
  }
  return TOP_LEVEL[first] ?? null;
}
