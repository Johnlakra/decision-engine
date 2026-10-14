/**
 * Read a stored decision for display. The decision is data from the API, so every field is
 * type-checked here; anything malformed is treated as absent, never rendered as-is.
 */

export interface OptionView {
  readonly id: string;
  readonly label: string;
}

type Decision = Readonly<Record<string, unknown>> | null | undefined;

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function optionsOf(decision: Decision): OptionView[] {
  const raw = decision?.options;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.flatMap((entry: unknown): OptionView[] => {
    if (!isRecord(entry) || typeof entry.id !== "string" || typeof entry.label !== "string") {
      return [];
    }
    return [{ id: entry.id, label: entry.label }];
  });
}

export function recommendedIdOf(decision: Decision): string | null {
  return typeof decision?.recommended === "string" ? decision.recommended : null;
}

export function rationaleOf(decision: Decision): string | null {
  return typeof decision?.rationale === "string" && decision.rationale.trim() !== ""
    ? decision.rationale
    : null;
}

export function confidenceOf(decision: Decision): number | null {
  const value = decision?.confidence;
  return typeof value === "number" && value >= 0 && value <= 1 ? value : null;
}

/** Options with the recommended one first (docs/UI_UX.md: recommended option is the primary button). */
export function orderedOptions(decision: Decision): OptionView[] {
  const recommended = recommendedIdOf(decision);
  const options = optionsOf(decision);
  const first = options.filter((option) => option.id === recommended);
  const rest = options.filter((option) => option.id !== recommended);
  return [...first, ...rest];
}

/** Move the focus by `delta`, stopping at the ends (no wrap, so j/k never jump unexpectedly). */
export function moveIndex(current: number, delta: number, length: number): number {
  if (length <= 0) {
    return 0;
  }
  return Math.min(Math.max(current + delta, 0), length - 1);
}
