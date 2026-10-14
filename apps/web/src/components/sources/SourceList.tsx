"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AddSourceForm } from "@/components/sources/AddSourceForm";
import { ApiError, fetchSources, setSourceEnabled, type SourceList as SourceListData, type SourceOut } from "@/lib/api/sources";
import { translate, type Locale } from "@/lib/i18n";
import { sourceHealth, type SourceHealth } from "@/lib/sources/health";
import { sortSources } from "@/lib/sources/form";

const QUERY_KEY = ["sources"] as const;
const FORBIDDEN = 403;
const HEALTH_MARK: Readonly<Record<SourceHealth, string>> = { ok: "●", failing: "▲", paused: "○" };
const HEALTH_COLOR: Readonly<Record<SourceHealth, string>> = {
  ok: "text-primary",
  failing: "text-danger",
  paused: "text-muted",
};

interface SourceListProps {
  readonly locale: Locale;
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

export function SourceList({ locale }: SourceListProps) {
  const t: Translate = (key, values) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: QUERY_KEY, queryFn: fetchSources });
  const [toggleError, setToggleError] = useState<string | null>(null);
  const rows = useMemo(() => sortSources(query.data?.data ?? []), [query.data]);

  const toggle = useMutation({
    mutationFn: (vars: { id: string; enabled: boolean }) => setSourceEnabled(vars.id, vars.enabled),
    onMutate: async (vars) => {
      setToggleError(null);
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous = queryClient.getQueryData<SourceListData>(QUERY_KEY);
      queryClient.setQueryData<SourceListData>(QUERY_KEY, (current) =>
        current === undefined
          ? current
          : { data: current.data.map((row) => (row.id === vars.id ? { ...row, enabled: vars.enabled } : row)) },
      );
      return { previous };
    },
    onError: (error, _vars, context) => {
      queryClient.setQueryData(QUERY_KEY, context?.previous);
      const denied = error instanceof ApiError && error.status === FORBIDDEN;
      setToggleError(t(denied ? "sources.toggle.admin" : "sources.toggle.error"));
    },
    onSettled: () => void queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });

  return (
    <section className="mx-auto max-w-[760px] space-y-3 p-4">
      <h1 className="text-[20px] font-semibold">{t("sources.title")}</h1>
      {query.isPending ? <p className="text-muted">{t("sources.loading")}</p> : null}
      {query.isError ? (
        <div>
          <p role="alert">{t("sources.error")}</p>
          <button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
            {t("queue.retry")}
          </button>
        </div>
      ) : null}
      {query.isSuccess && rows.length === 0 ? <p className="text-muted">{t("sources.empty")}</p> : null}
      {toggleError === null ? null : <p role="alert">{toggleError}</p>}
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.id}>
            <SourceCard
              row={row}
              locale={locale}
              onToggle={(enabled) => toggle.mutate({ id: row.id, enabled })}
            />
          </li>
        ))}
      </ul>
      <AddSourceForm locale={locale} />
    </section>
  );
}

interface SourceCardProps {
  readonly row: SourceOut;
  readonly locale: Locale;
  readonly onToggle: (enabled: boolean) => void;
}

function SourceCard({ row, locale, onToggle }: SourceCardProps) {
  const t: Translate = (key, values) => translate(locale, key, values);
  const health = sourceHealth(row);
  const healthText =
    health === "failing" ? t("sources.health.failing", { count: row.error_count }) : t(`sources.health.${health}`);
  const polled =
    row.last_polled_at === null
      ? t("sources.neverPolled")
      : t("sources.lastPolled", { when: new Date(row.last_polled_at).toLocaleString(locale) });
  return (
    <div className="rounded-[12px] border border-border bg-surface p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold">{row.name}</h2>
          <p className="text-[13px] text-muted">
            {t(`sources.type.${row.type}`)} · {row.slug}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={row.enabled}
          aria-label={row.name}
          onClick={() => onToggle(!row.enabled)}
          className="min-h-[44px] min-w-[72px] rounded-[8px] border border-border px-3 text-[14px]"
        >
          {row.enabled ? t("sources.on") : t("sources.off")}
        </button>
      </div>
      <p className="mt-2 text-[14px]">
        <span aria-hidden="true" className={HEALTH_COLOR[health]}>
          {HEALTH_MARK[health]}{" "}
        </span>
        <span>{healthText}</span>
      </p>
      <p className="text-[13px] text-muted">{polled}</p>
      <p className="text-[13px] text-muted">{t("sources.itemsToday", { count: row.items_today })}</p>
    </div>
  );
}
