import { describe, expect, it } from "vitest";
import { snoozePresets } from "./snooze";

// 2026-10-14 is a Wednesday. 10:00 UTC = 15:30 Asia/Kolkata.
const WEDNESDAY_NOON_UTC = new Date("2026-10-14T10:00:00Z");

describe("snoozePresets", () => {
  it("later today is exactly three hours ahead", () => {
    expect(snoozePresets(WEDNESDAY_NOON_UTC).laterToday).toBe("2026-10-14T13:00:00.000Z");
  });

  it("tomorrow is 09:00 Asia/Kolkata, which is 03:30 UTC", () => {
    expect(snoozePresets(WEDNESDAY_NOON_UTC).tomorrow).toBe("2026-10-15T03:30:00.000Z");
  });

  it("uses the Kolkata calendar day, not the UTC day, late in the evening", () => {
    // 20:00 UTC Wed = 01:30 Thu in Kolkata, so "tomorrow" is Friday 09:00 IST.
    const now = new Date("2026-10-14T20:00:00Z");
    expect(snoozePresets(now).tomorrow).toBe("2026-10-16T03:30:00.000Z");
  });

  it("next week is the coming Monday at 09:00 Asia/Kolkata", () => {
    expect(snoozePresets(WEDNESDAY_NOON_UTC).nextWeek).toBe("2026-10-19T03:30:00.000Z");
  });

  it("on a Monday, next week is seven days later, not today", () => {
    const monday = new Date("2026-10-12T02:00:00Z");
    expect(snoozePresets(monday).nextWeek).toBe("2026-10-19T03:30:00.000Z");
  });

  it("on a Sunday, next week is the next day", () => {
    const sunday = new Date("2026-10-18T10:00:00Z");
    expect(snoozePresets(sunday).nextWeek).toBe("2026-10-19T03:30:00.000Z");
  });

  it("treats Sunday evening UTC that is already Monday in Kolkata as Monday", () => {
    // 2026-10-18 20:00 UTC = Mon 01:30 IST, so next Monday is the 26th.
    const now = new Date("2026-10-18T20:00:00Z");
    expect(snoozePresets(now).nextWeek).toBe("2026-10-26T03:30:00.000Z");
  });

  it("returns ISO 8601 UTC strings that are all in the future", () => {
    const presets = snoozePresets(WEDNESDAY_NOON_UTC);
    for (const value of Object.values(presets)) {
      expect(value).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
      expect(new Date(value).getTime()).toBeGreaterThan(WEDNESDAY_NOON_UTC.getTime());
    }
  });
});
