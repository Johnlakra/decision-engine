import { translate, type Locale } from "@/lib/i18n";

/** Urgency shows an icon and a word, never colour alone (docs/UI_UX.md section 4). */

interface UrgencyBadgeProps {
  readonly urgency: number | null | undefined;
  readonly locale: Locale;
}

export function UrgencyBadge({ urgency, locale }: UrgencyBadgeProps) {
  if (urgency === null || urgency === undefined || urgency < 1) {
    return null;
  }
  const urgent = urgency >= 2;
  return (
    <span
      className={
        urgent
          ? "rounded-[8px] bg-surface-2 px-2 py-0.5 text-[12px] font-medium text-urgent"
          : "rounded-[8px] bg-surface-2 px-2 py-0.5 text-[12px] text-warning"
      }
    >
      <span aria-hidden="true">{urgent ? "▲ " : "● "}</span>
      {translate(locale, urgent ? "queue.urgency.urgent" : "queue.urgency.soon")}
    </span>
  );
}
