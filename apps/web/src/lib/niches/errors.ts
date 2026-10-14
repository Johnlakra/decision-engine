import { ApiError } from "@/lib/api/request";
import { pointerField, type FormField } from "./form";

/** Turns a failed PUT into what the editor shows (ADR 0011: pointers map to fields). */

const FORBIDDEN = 403;
const UNPROCESSABLE = 422;

export interface GeneralError {
  readonly pointer: string;
  readonly message: string;
}

export type SaveErrorView =
  | { readonly kind: "admin"; readonly fields: Record<string, never>; readonly general: readonly [] }
  | {
      readonly kind: "validation";
      readonly fields: Partial<Record<FormField, readonly string[]>>;
      readonly general: readonly GeneralError[];
      /** Every server error in order, for the YAML tab where no form field exists. */
      readonly all: readonly GeneralError[];
    }
  | { readonly kind: "other"; readonly fields: Record<string, never>; readonly general: readonly [] };

function readError(entry: unknown): GeneralError | null {
  if (typeof entry !== "object" || entry === null) {
    return null;
  }
  const { json_pointer: pointer, message } = entry as { json_pointer?: unknown; message?: unknown };
  return typeof pointer === "string" && typeof message === "string" ? { pointer, message } : null;
}

export function saveErrorView(error: unknown): SaveErrorView {
  if (!(error instanceof ApiError)) {
    return { kind: "other", fields: {}, general: [] };
  }
  if (error.status === FORBIDDEN) {
    return { kind: "admin", fields: {}, general: [] };
  }
  if (error.status !== UNPROCESSABLE) {
    return { kind: "other", fields: {}, general: [] };
  }
  const fields: Partial<Record<FormField, readonly string[]>> = {};
  const general: GeneralError[] = [];
  const all: GeneralError[] = [];
  for (const entry of error.errors) {
    const parsed = readError(entry);
    if (parsed === null) {
      continue;
    }
    all.push(parsed);
    const field = pointerField(parsed.pointer);
    if (field === null) {
      general.push(parsed);
    } else {
      fields[field] = [...(fields[field] ?? []), parsed.message];
    }
  }
  return { kind: "validation", fields, general, all };
}
