import { describe, expect, it } from "vitest";
import { formFromSettings, formToPayload, parseInterests, type SettingsForm } from "./form";

const VALID: SettingsForm = {
  quietFrom: "23",
  quietTo: "6",
  digestHour: "9",
  pingCap: "5",
  interests: " ai ,  crypto, ",
  languages: ["en", "pa"],
};

describe("formToPayload", () => {
  it("builds the exact SettingsIn shape with trimmed interests", () => {
    expect(formToPayload(VALID)).toEqual({
      ok: true,
      payload: {
        quiet_hours: [23, 6],
        digest_hour: 9,
        ping_cap_per_day: 5,
        interests: ["ai", "crypto"],
        languages: ["en", "pa"],
      },
    });
  });

  it("names every broken field so the form can highlight them", () => {
    const result = formToPayload({
      ...VALID,
      quietFrom: "25",
      digestHour: "x",
      pingCap: "51",
      languages: [],
    });

    expect(result).toEqual({
      ok: false,
      errors: ["quiet", "digestHour", "pingCap", "languages"],
    });
  });

  it("refuses more interests than the API allows", () => {
    const many = Array.from({ length: 21 }, (_, index) => `topic${index}`).join(",");

    expect(formToPayload({ ...VALID, interests: many })).toEqual({
      ok: false,
      errors: ["interests"],
    });
  });
});

describe("parseInterests", () => {
  it("drops empty entries and rejects an over-long one", () => {
    expect(parseInterests("a,,  b ,")).toEqual(["a", "b"]);
    expect(parseInterests("x".repeat(61))).toBeNull();
  });
});

describe("formFromSettings", () => {
  it("round-trips the saved settings into the form", () => {
    const form = formFromSettings({
      quiet_hours: [22, 7],
      digest_hour: 8,
      ping_cap_per_day: 3,
      interests: ["ai", "crypto"],
      languages: ["en"],
    });

    expect(form).toEqual({
      quietFrom: "22",
      quietTo: "7",
      digestHour: "8",
      pingCap: "3",
      interests: "ai, crypto",
      languages: ["en"],
    });
  });
});
