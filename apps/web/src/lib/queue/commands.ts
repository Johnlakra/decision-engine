/** Command palette list and matcher (docs/UI_UX.md, Cmd-K). Pure: no React, no router. */

export type PaletteCommandId =
  | "approve"
  | "reject"
  | "snooze"
  | "open"
  | "bulk"
  | "next"
  | "previous"
  | "help"
  | "goQueue"
  | "goHistory"
  | "goSettings";

export interface PaletteCommand {
  readonly id: PaletteCommandId;
  /** Message catalog key for the visible label. */
  readonly labelKey: string;
}

const IDS: readonly PaletteCommandId[] = [
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
];

export const COMMANDS: readonly PaletteCommand[] = IDS.map((id) => ({
  id,
  labelKey: `palette.cmd.${id}`,
}));

/**
 * Keep commands whose label contains every query word (case-insensitive).
 * Labels starting with the first word come first; otherwise list order is kept.
 */
export function filterCommands(
  commands: readonly PaletteCommand[],
  query: string,
  labelOf: (command: PaletteCommand) => string,
): readonly PaletteCommand[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return commands;
  }
  const matches = commands.filter((command) => {
    const label = labelOf(command).toLowerCase();
    return words.every((word) => label.includes(word));
  });
  const startsWithFirst = (command: PaletteCommand) =>
    labelOf(command).toLowerCase().startsWith(words[0] ?? "");
  return [...matches.filter(startsWithFirst), ...matches.filter((c) => !startsWithFirst(c))];
}
