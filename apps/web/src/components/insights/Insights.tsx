"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStatsToday, type StatsToday } from "@/lib/api/stats";
import { translate, type Locale } from "@/lib/i18n";
import { budgetView, nicheCounts, type BudgetLevel } from "@/lib/insights/budget";

/** Refresh every 20 s, like the queue. */
const REFRESH_MS = 20_000;
const LAYA_MODES: readonly string[] = ["off", "shadow", "on"];
const BAR_COLOR: Readonly<Record<BudgetLevel, string>> = {
  ok: "bg-primary",
  warning: "bg-warning",
  exhausted: "bg-danger",
  unlimited: "bg-muted",
};

interface InsightsProps {
  readonly locale: Locale;
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

export function Insights({ locale }: InsightsProps) {
  const t: Translate = (key, values) => translate(locale, key, values);
  const query = useQuery({ queryKey: ["stats", "today"], queryFn: fetchStatsToday, refetchInterval: REFRESH_MS });

  if (query.isPending) {
    return <p className="p-6 text-muted">{t("insights.loading")}</p>;
  }
  if (query.isError) {
    return (
      <div className="p-6">
        <p role="alert">{t("insights.error")}</p>
        <button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
          {t("queue.retry")}
        </button>
      </div>
    );
  }
  return <InsightsBody stats={query.data} t={t} />;
}

function InsightsBody({ stats, t }: { readonly stats: StatsToday; readonly t: Translate }) {
  const tiles = [
    { label: t("insights.itemsIn"), value: stats.items_in },
    { label: t("insights.decided"), value: stats.decided },
    { label: t("insights.autoHandled"), value: stats.auto_handled },
    { label: t("insights.discarded"), value: stats.discarded },
  ];
  const niches = nicheCounts(stats.by_niche);
  const mode = LAYA_MODES.includes(stats.laya_mode) ? t(`niches.laya.${stats.laya_mode}`) : stats.laya_mode;
  return (
    <section className="mx-auto max-w-[760px] space-y-5 p-4">
      <h1 className="text-[20px] font-semibold">{t("insights.title")}</h1>
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {tiles.map((tile) => (
          <div key={tile.label} className="rounded-[12px] border border-border bg-surface p-3">
            <dt className="text-[13px] text-muted">{tile.label}</dt>
            <dd className="text-[24px] font-semibold">{tile.value}</dd>
          </div>
        ))}
      </dl>
      <div className="space-y-2">
        <h2 className="text-[16px] font-semibold">{t("insights.budgets")}</h2>
        {stats.llm.length === 0 ? <p className="text-muted">{t("insights.noBudgets")}</p> : null}
        {stats.llm.map((budget) => (
          <BudgetBar key={budget.provider} budget={budget} t={t} />
        ))}
      </div>
      <div className="space-y-2">
        <h2 className="text-[16px] font-semibold">{t("insights.byNiche")}</h2>
        {niches.length === 0 ? <p className="text-muted">{t("insights.noNiches")}</p> : null}
        <ul className="space-y-1 text-[14px]">
          {niches.map((niche) => (
            <li key={niche.name} className="flex justify-between rounded-[8px] border border-border bg-surface px-3 py-2">
              <span>{niche.name}</span>
              <span>{niche.count}</span>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-[14px]">{t("niches.laya", { mode })}</p>
    </section>
  );
}

function BudgetBar({ budget, t }: { readonly budget: StatsToday["llm"][number]; t: Translate }) {
  const view = budgetView(budget);
  const detail =
    view.limit === null
      ? t("insights.requestsNoLimit", { used: view.used })
      : t("insights.requestsUsed", { used: view.used, limit: view.limit });
  const status = view.level === "warning" ? t("insights.nearLimit") : view.level === "exhausted" ? t("insights.limitReached") : null;
  return (
    <div className="rounded-[12px] border border-border bg-surface p-3">
      <div className="flex justify-between text-[14px]">
        <span className="font-medium">{view.provider}</span>
        {status === null ? null : <span className="font-semibold">{status}</span>}
      </div>
      <div
        role="progressbar"
        aria-label={view.provider}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={view.percent}
        aria-valuetext={detail}
        className="mt-1 h-2 w-full overflow-hidden rounded-full bg-border"
      >
        <div className={`h-full ${BAR_COLOR[view.level]}`} style={{ width: `${view.percent}%` }} />
      </div>
      <p className="mt-1 text-[13px] text-muted">{detail}</p>
    </div>
  );
}
