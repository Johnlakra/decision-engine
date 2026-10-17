"use client";

import { translate, type Locale } from "@/lib/i18n";
import type { FilterChoices, QueueFilter } from "@/lib/queue/filters";

interface FilterChipsProps {
  readonly locale: Locale;
  readonly choices: FilterChoices;
  readonly filter: QueueFilter;
  readonly onChange: (filter: QueueFilter) => void;
}

const CHIP_BASE = "rounded-full border px-3 py-1 text-[13px]";
const CHIP_ON = "border-primary bg-primary text-primary-text";
const CHIP_OFF = "border-border bg-surface text-text";

function chipClass(active: boolean): string {
  return `${CHIP_BASE} ${active ? CHIP_ON : CHIP_OFF}`;
}

interface ChipRowProps {
  readonly groupLabel: string;
  readonly allLabel: string;
  readonly values: readonly string[];
  readonly active: string | null;
  readonly onPick: (value: string | null) => void;
}

function ChipRow({ groupLabel, allLabel, values, active, onPick }: ChipRowProps) {
  return (
    <div role="group" aria-label={groupLabel} className="flex flex-wrap gap-2">
      <button
        type="button"
        aria-pressed={active === null}
        aria-label={allLabel}
        className={chipClass(active === null)}
        onClick={() => onPick(null)}
      >
        {allLabel}
      </button>
      {values.map((value) => (
        <button
          key={value}
          type="button"
          aria-pressed={active === value}
          className={chipClass(active === value)}
          onClick={() => onPick(value)}
        >
          {value}
        </button>
      ))}
    </div>
  );
}

export function FilterChips({ locale, choices, filter, onChange }: FilterChipsProps) {
  const t = (key: string) => translate(locale, key);
  if (choices.niches.length === 0 && choices.sources.length === 0) {
    return null;
  }
  return (
    <div className="space-y-2 px-4">
      <ChipRow
        groupLabel={t("queue.filter.niche")}
        allLabel={t("queue.filter.allNiches")}
        values={choices.niches}
        active={filter.niche}
        onPick={(niche) => onChange({ ...filter, niche })}
      />
      <ChipRow
        groupLabel={t("queue.filter.source")}
        allLabel={t("queue.filter.allSources")}
        values={choices.sources}
        active={filter.source}
        onPick={(source) => onChange({ ...filter, source })}
      />
    </div>
  );
}
