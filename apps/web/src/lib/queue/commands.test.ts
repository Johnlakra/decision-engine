import { describe, expect, it } from "vitest";
import { COMMANDS, filterCommands, type PaletteCommand } from "./commands";

const label = (command: PaletteCommand) => command.id.toLowerCase();

describe("COMMANDS", () => {
  it("lists the eleven palette commands with unique ids", () => {
    expect(COMMANDS.map((command) => command.id)).toEqual([
      "approve",
      "reject",
      "snooze",
      "open",
      "bulk",
      "next",
      "previous",
      "help",
      "goQueue",
      "goHistory",
      "goSettings",
    ]);
  });

  it("gives every command a message key", () => {
    for (const command of COMMANDS) {
      expect(command.labelKey).toBe(`palette.cmd.${command.id}`);
    }
  });
});

describe("filterCommands", () => {
  it("returns every command for an empty or blank query", () => {
    expect(filterCommands(COMMANDS, "", label)).toHaveLength(COMMANDS.length);
    expect(filterCommands(COMMANDS, "   ", label)).toHaveLength(COMMANDS.length);
  });

  it("matches case-insensitively on the label", () => {
    expect(filterCommands(COMMANDS, "GOHIS", label).map((c) => c.id)).toEqual(["goHistory"]);
  });

  it("requires every word to match, in any order", () => {
    const words = (command: PaletteCommand) =>
      (({ goHistory: "Go to History", goQueue: "Go to Queue" }) as Record<string, string>)[command.id] ?? "other";
    expect(filterCommands(COMMANDS, "history go", words).map((c) => c.id)).toEqual(["goHistory"]);
  });

  it("ranks prefix matches before later matches", () => {
    const text = (command: PaletteCommand) =>
      (({ next: "Next item", previous: "Previous item", open: "Open item" }) as Record<string, string>)[command.id] ?? "zzz";
    expect(filterCommands(COMMANDS, "item", text).map((c) => c.id)).toEqual(["open", "next", "previous"]);
    expect(filterCommands(COMMANDS, "pre", text).map((c) => c.id)).toEqual(["previous"]);
  });

  it("returns an empty list when nothing matches", () => {
    expect(filterCommands(COMMANDS, "qqqq", label)).toEqual([]);
  });
});
