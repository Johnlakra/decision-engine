import { translate, type Locale } from "@/lib/i18n";

interface BulkBarProps {
  readonly locale: Locale;
  readonly count: number;
  readonly onApprove: () => void;
  readonly onExit: () => void;
}

/** Shown in bulk mode: selected count and the one bulk action (docs/UI_UX.md: Bulk mode). */
export function BulkBar({ locale, count, onApprove, onExit }: BulkBarProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 rounded-[10px] border border-border bg-surface-2 p-3">
      <button
        type="button"
        disabled={count === 0}
        onClick={onApprove}
        className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-50"
      >
        {t("queue.bulk.approve", { count })}
      </button>
      <span className="text-[13px] text-muted">{t("queue.bulk.selected", { count })}</span>
      <button type="button" onClick={onExit} className="ml-auto text-[13px] underline underline-offset-4">
        {t("queue.bulk.exit")}
      </button>
    </div>
  );
}
