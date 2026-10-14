/**
 * Confidence words for cards (docs/UI_UX.md section 6: words, never raw percentages).
 * Thresholds: High >= 0.8 (spec); Medium >= 0.5 (our choice, the spec left it open).
 */

export const HIGH_CONFIDENCE = 0.8;
export const MEDIUM_CONFIDENCE = 0.5;

export type ConfidenceLabel = "high" | "medium" | "low";

export function confidenceLabel(value: number | null | undefined): ConfidenceLabel | null {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return null;
  }
  if (value >= HIGH_CONFIDENCE) {
    return "high";
  }
  return value >= MEDIUM_CONFIDENCE ? "medium" : "low";
}
