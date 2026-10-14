import { describe, expect, it } from "vitest";
import { applyFormField, formFromConfig, parseLines, pointerField } from "./form";

const CONFIG = {
  name: "inbox",
  label: "Inbox",
  description: "a personal email",
  autonomy: "ask",
  actions: ["archive", "draft_reply"],
  auto_actions: [],
  notify: { urgent_ping: true, digest: false, min_urgency_for_ping: 1 },
  prompt: "keep me",
};

describe("formFromConfig", () => {
  it("reads the editable fields", () => {
    expect(formFromConfig(CONFIG)).toEqual({
      label: "Inbox",
      description: "a personal email",
      autonomy: "ask",
      actions: "archive\ndraft_reply",
      autoActions: "",
      urgentPing: true,
      digest: false,
      minUrgencyForPing: "1",
    });
  });

  it("falls back to API defaults for missing or wrong-typed values", () => {
    const form = formFromConfig({ label: 3, actions: "x" });
    expect(form.label).toBe("");
    expect(form.actions).toBe("");
    expect(form.autonomy).toBe("ask");
    expect(form.urgentPing).toBe(true);
    expect(form.minUrgencyForPing).toBe("2");
  });
});

describe("applyFormField", () => {
  it("changes one field and keeps every other key, without mutating the input", () => {
    const next = applyFormField(CONFIG, "autonomy", "suggest");

    expect(next).toEqual({ ...CONFIG, autonomy: "suggest" });
    expect(CONFIG.autonomy).toBe("ask");
  });

  it("turns lines into a trimmed list", () => {
    expect(applyFormField(CONFIG, "actions", " a \n\nb\n").actions).toEqual(["a", "b"]);
    expect(parseLines("")).toEqual([]);
  });

  it("writes notify keys while keeping the others", () => {
    const next = applyFormField(CONFIG, "digest", true);
    expect(next.notify).toEqual({ urgent_ping: true, digest: true, min_urgency_for_ping: 1 });
  });

  it("stores min urgency as a number, and leaves non-numbers for the server to reject", () => {
    expect(applyFormField(CONFIG, "minUrgencyForPing", "0").notify).toMatchObject({ min_urgency_for_ping: 0 });
    expect(applyFormField(CONFIG, "minUrgencyForPing", "x").notify).toMatchObject({ min_urgency_for_ping: "x" });
  });
});

describe("pointerField", () => {
  it("maps a pointer to the field it names", () => {
    expect(pointerField("/autonomy")).toBe("autonomy");
    expect(pointerField("/auto_actions/0")).toBe("autoActions");
    expect(pointerField("/actions/2")).toBe("actions");
    expect(pointerField("/notify/min_urgency_for_ping")).toBe("minUrgencyForPing");
    expect(pointerField("/notify/digest")).toBe("digest");
  });

  it("returns null for pointers without a form field", () => {
    expect(pointerField("")).toBeNull();
    expect(pointerField("/prompt")).toBeNull();
    expect(pointerField("/expert_review/always")).toBeNull();
    expect(pointerField("/notify")).toBeNull();
  });
});
