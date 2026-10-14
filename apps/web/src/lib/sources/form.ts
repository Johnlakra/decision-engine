import type { components } from "@decision-engine/client";
import { ApiError } from "@/lib/api/request";

/** Add-source form rules. Limits mirror apps/api/app/schemas/sources.py (ADR 0010, FR-90). */

export const SOURCE_TYPES = ["rss", "google_news"] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];
export type SourceCreate = components["schemas"]["SourceIn"];

export const MAX_NAME_CHARS = 120;
export const MAX_URL_CHARS = 2048;
export const MAX_QUERY_CHARS = 200;
const SLUG_PATTERN = /^[a-z][a-z0-9-]{1,59}$/;
const MAX_SLUG_CHARS = 60;
const CONFLICT = 409;
const FORBIDDEN = 403;
const UNPROCESSABLE = 422;

export type SourceField = "type" | "name" | "slug" | "value";
export interface SourceDraft {
  readonly type: SourceType;
  readonly name: string;
  readonly slug: string;
  readonly value: string;
}
/** Message keys, not text, so the form can translate them. */
export type SourceFieldErrors = Partial<Record<SourceField, string>>;

function validateValue(draft: SourceDraft): string | undefined {
  const value = draft.value.trim();
  if (value === "") {
    return "sources.error.valueRequired";
  }
  if (draft.type === "google_news") {
    return value.length > MAX_QUERY_CHARS ? "sources.error.queryTooLong" : undefined;
  }
  if (value.length > MAX_URL_CHARS) {
    return "sources.error.urlTooLong";
  }
  return value.startsWith("https://") && value.length > "https://".length ? undefined : "sources.error.urlHttps";
}

export function validateSource(draft: SourceDraft): SourceFieldErrors {
  const errors: { -readonly [K in SourceField]?: string } = {};
  const name = draft.name.trim();
  if (name === "") {
    errors.name = "sources.error.nameRequired";
  } else if (name.length > MAX_NAME_CHARS) {
    errors.name = "sources.error.nameTooLong";
  }
  if (!SLUG_PATTERN.test(draft.slug)) {
    errors.slug = "sources.error.slugFormat";
  }
  const valueError = validateValue(draft);
  if (valueError !== undefined) {
    errors.value = valueError;
  }
  return errors;
}

export function buildSourceBody(draft: SourceDraft): SourceCreate {
  const value = draft.value.trim();
  return {
    type: draft.type,
    name: draft.name.trim(),
    slug: draft.slug,
    config: draft.type === "rss" ? { url: value } : { query: value },
  };
}

/** Suggest a slug from a name: lowercase letters, digits and hyphens, starting with a letter. */
export function slugFromName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^[^a-z]+/, "")
    .replace(/-+$/, "")
    .slice(0, MAX_SLUG_CHARS);
}

export function sortSources<T extends { readonly name: string }>(rows: readonly T[]): T[] {
  return [...rows].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
}

export type SourceErrorView =
  | { readonly kind: "slugTaken" | "admin" | "other"; readonly fields: Record<string, never>; readonly general: readonly [] }
  | {
      readonly kind: "validation";
      readonly fields: Partial<Record<SourceField, readonly string[]>>;
      readonly general: readonly string[];
    };

function fieldOf(raw: string): SourceField | null {
  const head = raw.replace(/^body\./, "").split(".")[0];
  if (head === "config") {
    return "value";
  }
  return head === "type" || head === "name" || head === "slug" ? head : null;
}

function readEntry(entry: unknown): { field: string; message: string } | null {
  if (typeof entry !== "object" || entry === null) {
    return null;
  }
  const { field, message } = entry as { field?: unknown; message?: unknown };
  return typeof message === "string" ? { field: typeof field === "string" ? field : "", message } : null;
}

export function sourceErrorView(error: unknown): SourceErrorView {
  if (!(error instanceof ApiError)) {
    return { kind: "other", fields: {}, general: [] };
  }
  if (error.status === CONFLICT) {
    return { kind: "slugTaken", fields: {}, general: [] };
  }
  if (error.status === FORBIDDEN) {
    return { kind: "admin", fields: {}, general: [] };
  }
  if (error.status !== UNPROCESSABLE) {
    return { kind: "other", fields: {}, general: [] };
  }
  const fields: Partial<Record<SourceField, readonly string[]>> = {};
  const general: string[] = [];
  for (const raw of error.errors) {
    const entry = readEntry(raw);
    if (entry === null) {
      continue;
    }
    const field = fieldOf(entry.field);
    if (field === null) {
      general.push(entry.message);
    } else {
      fields[field] = [...(fields[field] ?? []), entry.message];
    }
  }
  return { kind: "validation", fields, general };
}
