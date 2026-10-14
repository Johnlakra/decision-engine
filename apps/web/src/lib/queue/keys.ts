/** Queue keyboard map (docs/UI_UX.md section 3, Queue "Keys"). Pure: key in, action out. */

export type QueueAction =
  | { type: "approve" }
  | { type: "reject" }
  | { type: "snooze" }
  | { type: "edit" }
  | { type: "next" }
  | { type: "previous" }
  | { type: "choose"; index: number }
  | { type: "open" }
  | { type: "help" }
  | { type: "bulk" }
  | { type: "select" }
  | { type: "exitBulk" };

const CHOICE_KEYS = ["1", "2", "3", "4", "5"];

const KEY_ACTIONS: ReadonlyMap<string, QueueAction> = new Map<string, QueueAction>([
  ["a", { type: "approve" }],
  ["r", { type: "reject" }],
  ["s", { type: "snooze" }],
  ["e", { type: "edit" }],
  ["j", { type: "next" }],
  ["k", { type: "previous" }],
  ["o", { type: "open" }],
  ["?", { type: "help" }],
  ["b", { type: "bulk" }],
  [" ", { type: "select" }],
  ["Escape", { type: "exitBulk" }],
]);

export function queueActionForKey(key: string): QueueAction | null {
  const direct = KEY_ACTIONS.get(key);
  if (direct) {
    return direct;
  }
  const choice = CHOICE_KEYS.indexOf(key);
  return choice === -1 ? null : { type: "choose", index: choice };
}
