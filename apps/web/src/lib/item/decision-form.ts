import type { DecisionBody } from "@/lib/api/items";

/**
 * Builds the body for `POST /v1/items/{id}/decision` from the detail form. Pure.
 * Limits mirror the API: a note is at most 1000 characters (DecisionIn.note).
 */

export const NOTE_MAX_CHARS = 1000;

export type FormVerdict = "approve" | "edit" | "reject";

export interface DecisionFormState {
  readonly option: string | null;
  readonly note: string;
}

export type DecisionFormResult =
  | { readonly ok: true; readonly body: DecisionBody }
  | { readonly ok: false; readonly error: "note_too_long" | "option_required" };

export function buildDecisionBody(form: DecisionFormState, verdict: FormVerdict): DecisionFormResult {
  const note = form.note.trim();
  if (note.length > NOTE_MAX_CHARS) {
    return { ok: false, error: "note_too_long" };
  }
  if (verdict === "edit" && !form.option) {
    return { ok: false, error: "option_required" };
  }
  const body: DecisionBody = { verdict };
  if (form.option) {
    body.option = form.option;
  }
  if (note) {
    body.note = note;
  }
  return { ok: true, body };
}
