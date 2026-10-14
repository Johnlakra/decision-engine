import { confidenceLabel, type ConfidenceLabel } from "@/lib/queue/confidence";

/**
 * Reads the stored triage record for the Triage tab (docs/UI_UX.md, item detail). The record is
 * data from the API: fields are type-checked, and bad entries are dropped, never rendered raw.
 */

export interface TriageAnswerView {
  readonly question: string;
  readonly choice: string | null;
  readonly confidence: ConfidenceLabel | null;
  readonly source: string;
}

export interface TriageView {
  readonly mode: string | null;
  readonly decidedBy: string | null;
  readonly model: string | null;
  readonly latencyMs: number | null;
  readonly answers: readonly TriageAnswerView[];
}

type Obj = Readonly<Record<string, unknown>>;

function isObject(value: unknown): value is Obj {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function textOrNull(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function answerView(question: string, raw: unknown): TriageAnswerView | null {
  if (!isObject(raw)) {
    return null;
  }
  const confidence = typeof raw.confidence === "number" ? raw.confidence : null;
  return {
    question,
    choice: textOrNull(raw.choice),
    confidence: confidenceLabel(confidence),
    source: textOrNull(raw.source) ?? "unknown",
  };
}

export function summarizeTriage(triage: unknown): TriageView | null {
  if (!isObject(triage)) {
    return null;
  }
  const rawAnswers = isObject(triage.answers) ? triage.answers : {};
  const answers = Object.entries(rawAnswers).flatMap(([question, raw]) => {
    const view = answerView(question, raw);
    return view ? [view] : [];
  });
  const latency = typeof triage.latency_ms === "number" ? triage.latency_ms : null;
  return {
    mode: textOrNull(triage.mode),
    decidedBy: textOrNull(triage.decided_by),
    model: textOrNull(triage.model),
    latencyMs: latency,
    answers,
  };
}
