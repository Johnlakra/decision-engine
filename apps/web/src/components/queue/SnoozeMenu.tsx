"use client";

import { useEffect, useRef } from "react";
import { translate, type Locale } from "@/lib/i18n";
import { SNOOZE_KEYS, type SnoozePresetKey } from "@/lib/queue/snooze";

interface SnoozeMenuProps {
  readonly locale: Locale;
  readonly onPick: (preset: SnoozePresetKey) => void;
  readonly onClose: () => void;
}

const ENTRIES: readonly { key: string; preset: SnoozePresetKey; label: string }[] = [
  { key: "1", preset: SNOOZE_KEYS["1"] as SnoozePresetKey, label: "queue.snooze.laterToday" },
  { key: "2", preset: SNOOZE_KEYS["2"] as SnoozePresetKey, label: "queue.snooze.tomorrow" },
  { key: "3", preset: SNOOZE_KEYS["3"] as SnoozePresetKey, label: "queue.snooze.nextWeek" },
];

/** Small preset menu for `s`. Keys 1-3 and Escape are handled by QueueView's key handler. */
export function SnoozeMenu({ locale, onPick, onClose }: SnoozeMenuProps) {
  const t = (key: string) => translate(locale, key);
  const firstRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    firstRef.current?.focus();
  }, []);

  return (
    <div
      role="menu"
      aria-label={t("queue.snooze.title")}
      className="fixed bottom-20 left-1/2 w-[min(320px,90vw)] -translate-x-1/2 rounded-[10px] border border-border bg-surface p-2 shadow"
    >
      <p className="px-2 py-1 text-[13px] text-muted">{t("queue.snooze.title")}</p>
      {ENTRIES.map((entry, index) => (
        <button
          key={entry.preset}
          ref={index === 0 ? firstRef : undefined}
          type="button"
          role="menuitem"
          onClick={() => onPick(entry.preset)}
          className="flex w-full items-center justify-between rounded-[8px] px-2 py-2 text-left text-[14px] hover:bg-surface-2"
        >
          <span>{t(entry.label)}</span>
          <kbd className="text-[12px] text-muted">{entry.key}</kbd>
        </button>
      ))}
      <button
        type="button"
        onClick={onClose}
        className="mt-1 w-full rounded-[8px] px-2 py-2 text-left text-[13px] text-muted hover:bg-surface-2"
      >
        {t("queue.snooze.close")}
      </button>
    </div>
  );
}
