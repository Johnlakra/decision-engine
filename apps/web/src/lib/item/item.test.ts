import { describe, expect, it } from "vitest";
import { NOTE_MAX_CHARS, buildDecisionBody } from "./decision-form";
import { summarizeTriage } from "./triage";

describe("buildDecisionBody", () => {
  it("sends only the fields that were filled in", () => {
    const result = buildDecisionBody({ option: "B", note: "" }, "approve");

    expect(result).toEqual({ ok: true, body: { verdict: "approve", option: "B" } });
  });

  it("trims the note and sends no edits, because the backend does not consume a draft", () => {
    const result = buildDecisionBody({ option: "A", note: " Too late for me " }, "edit");

    expect(result).toEqual({
      ok: true,
      body: {
        verdict: "edit",
        option: "A",
        note: "Too late for me",
      },
    });
  });

  it("refuses an edit without an option and over-long text", () => {
    expect(buildDecisionBody({ option: null, note: "" }, "edit")).toEqual({
      ok: false,
      error: "option_required",
    });
    expect(
      buildDecisionBody({ option: "A", note: "x".repeat(NOTE_MAX_CHARS + 1) }, "edit"),
    ).toEqual({ ok: false, error: "note_too_long" });
  });
});

describe("summarizeTriage", () => {
  it("reads the record and words the confidence", () => {
    const view = summarizeTriage({
      mode: "shadow",
      decided_by: "llm_fallback",
      model: "gemini",
      latency_ms: 412,
      answers: {
        keep: { choice: "B", confidence: 0.9, source: "llm_fallback" },
        topic: { choice: "ai", confidence: 0.4, source: "laya" },
      },
    });

    expect(view).toEqual({
      mode: "shadow",
      decidedBy: "llm_fallback",
      model: "gemini",
      latencyMs: 412,
      answers: [
        { question: "keep", choice: "B", confidence: "high", source: "llm_fallback" },
        { question: "topic", choice: "ai", confidence: "low", source: "laya" },
      ],
    });
  });

  it("drops malformed answers and returns null for a missing record", () => {
    const view = summarizeTriage({ answers: { keep: "nope", topic: { choice: "ai" } } });

    expect(view?.answers.map((answer) => answer.question)).toEqual(["topic"]);
    expect(summarizeTriage(null)).toBeNull();
    expect(summarizeTriage(["not", "a", "record"])).toBeNull();
  });
});
