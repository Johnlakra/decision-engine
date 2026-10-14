"use client";

import { translate, type Locale } from "@/lib/i18n";

export type DetailTab = "decision" | "content" | "triage" | "activity";

const TABS: readonly DetailTab[] = ["decision", "content", "triage", "activity"];

interface ItemTabsProps {
  readonly active: DetailTab;
  readonly locale: Locale;
  readonly onChange: (tab: DetailTab) => void;
}

/** Tab strip with arrow-key movement (WAI-ARIA tabs pattern). */
export function ItemTabs({ active, locale, onChange }: ItemTabsProps) {
  function move(current: DetailTab, delta: number) {
    const index = TABS.indexOf(current);
    const next = TABS[(index + delta + TABS.length) % TABS.length];
    if (next) {
      onChange(next);
    }
  }

  return (
    <div
      role="tablist"
      aria-label={translate(locale, "item.tabs.label")}
      className="flex flex-wrap gap-2 border-b border-border"
    >
      {TABS.map((tab) => {
        const selected = tab === active;
        return (
          <button
            key={tab}
            id={`tab-${tab}`}
            role="tab"
            type="button"
            aria-selected={selected}
            aria-controls="item-panel"
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight") {
                move(tab, 1);
              } else if (event.key === "ArrowLeft") {
                move(tab, -1);
              }
            }}
            className={
              selected
                ? "border-b-2 border-primary px-3 py-2 text-[14px] font-semibold"
                : "px-3 py-2 text-[14px] text-muted"
            }
          >
            {translate(locale, `item.tabs.${tab}`)}
          </button>
        );
      })}
    </div>
  );
}
