/**
 * Snooze presets (owner decision Q2): always computed in the tenant zone, Asia/Kolkata,
 * so every device shows the same times. Pure: `now` is a parameter.
 * India has no daylight saving, so a fixed +05:30 offset is exact.
 */

export const TENANT_TIME_ZONE = "Asia/Kolkata";

const KOLKATA_OFFSET_MS = 5.5 * 60 * 60 * 1000;
const LATER_TODAY_MS = 3 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;
const MORNING_HOUR = 9;
const MONDAY = 1;
const DAYS_IN_WEEK = 7;

export interface SnoozePresets {
  readonly laterToday: string;
  readonly tomorrow: string;
  readonly nextWeek: string;
}

/** Midnight (as a UTC instant) of the Kolkata calendar day that contains `now`, shifted by whole days. */
function kolkataMorning(now: Date, addDays: number): string {
  const wallClock = now.getTime() + KOLKATA_OFFSET_MS;
  const wallMidnight = Math.floor(wallClock / DAY_MS) * DAY_MS;
  const target = wallMidnight + addDays * DAY_MS + MORNING_HOUR * 60 * 60 * 1000 - KOLKATA_OFFSET_MS;
  return new Date(target).toISOString();
}

function daysUntilNextMonday(now: Date): number {
  const weekday = new Date(now.getTime() + KOLKATA_OFFSET_MS).getUTCDay();
  const ahead = (MONDAY - weekday + DAYS_IN_WEEK) % DAYS_IN_WEEK;
  return ahead === 0 ? DAYS_IN_WEEK : ahead;
}

export function snoozePresets(now: Date): SnoozePresets {
  return {
    laterToday: new Date(now.getTime() + LATER_TODAY_MS).toISOString(),
    tomorrow: kolkataMorning(now, 1),
    nextWeek: kolkataMorning(now, daysUntilNextMonday(now)),
  };
}

export type SnoozePresetKey = keyof SnoozePresets;

/** Menu key to preset: 1 later today, 2 tomorrow, 3 next week. */
export const SNOOZE_KEYS: Readonly<Record<string, SnoozePresetKey>> = {
  "1": "laterToday",
  "2": "tomorrow",
  "3": "nextWeek",
};
