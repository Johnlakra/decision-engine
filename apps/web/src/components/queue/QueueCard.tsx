import type { ItemOut } from "@/lib/api/items";
import { translate, type Locale } from "@/lib/i18n";
import { confidenceLabel } from "@/lib/queue/confidence";
import { confidenceOf, orderedOptions, rationaleOf, recommendedIdOf } from "@/lib/queue/view";
import { UrgencyBadge } from "./UrgencyBadge";

interface QueueCardProps {
  readonly item: ItemOut;
  readonly locale: Locale;
  readonly disabled: boolean;
  readonly onChoose: (optionId: string) => void;
  readonly onReject: () => void;
}

const CONFIDENCE_KEYS = {
  high: "queue.confidence.high",
  medium: "queue.confidence.medium",
  low: "queue.confidence.low",
} as const;

const PRIMARY_BUTTON =
  "rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-50";
const SECONDARY_BUTTON =
  "rounded-[8px] border border-border px-4 py-2 text-[14px] text-text disabled:opacity-50";

export function QueueCard({ item, locale, disabled, onChoose, onReject }: QueueCardProps) {
  const t = (key: string) => translate(locale, key);
  const decision = item.decision;
  const options = orderedOptions(decision);
  const recommendedId = recommendedIdOf(decision);
  const recommendedLabel = options.find((option) => option.id === recommendedId)?.label;
  const confidence = confidenceLabel(confidenceOf(decision));
  const rationale = rationaleOf(decision);
  const summary = item.content?.summary ?? item.content?.body ?? "";

  return (
    <article
      className="rounded-[10px] border border-border bg-surface p-4"
      aria-labelledby="focused-title"
    >
      <header className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
        <span>{item.source}</span>
        <UrgencyBadge urgency={item.urgency} locale={locale} />
      </header>
      <h2 id="focused-title" className="mt-2 text-[17px] font-semibold text-text">
        {item.content?.title ?? "—"}
      </h2>
      {summary ? <p className="mt-1 line-clamp-2 text-[13px] text-muted">{summary}</p> : null}

      {recommendedLabel ? (
        <p className="mt-3 text-[13px]">
          <span className="font-medium">{t("queue.recommended")}:</span> {recommendedLabel}
          {confidence ? (
            <span className="ml-2 rounded-[8px] bg-surface-2 px-2 py-0.5 text-[12px]">
              {t(CONFIDENCE_KEYS[confidence])}
            </span>
          ) : null}
        </p>
      ) : null}

      {rationale ? (
        <details className="mt-3 text-[13px]">
          <summary className="cursor-pointer text-muted">{t("queue.why")}</summary>
          <p className="mt-2">{rationale}</p>
        </details>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {options.map((option, index) => (
          <button
            key={option.id}
            type="button"
            disabled={disabled}
            onClick={() => onChoose(option.id)}
            aria-keyshortcuts={index < 5 ? String(index + 1) : undefined}
            className={option.id === recommendedId ? PRIMARY_BUTTON : SECONDARY_BUTTON}
          >
            {option.label}
          </button>
        ))}
        <button type="button" disabled={disabled} onClick={onReject} className={SECONDARY_BUTTON}>
          {t("queue.reject")}
        </button>
      </div>
    </article>
  );
}
