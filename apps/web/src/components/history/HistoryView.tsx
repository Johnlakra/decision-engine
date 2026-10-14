"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import type { ItemOut, ItemPage } from "@/lib/api/items";
import { requestJson } from "@/lib/api/request";
import { translate, type Locale } from "@/lib/i18n";
import { historyPath, type HistoryFilters } from "@/lib/history/query";

const NO_FILTERS: HistoryFilters = { niche: "", source: "", q: "" };
const INPUT = "mt-1 w-full rounded-[8px] border border-border bg-surface p-2 text-[14px]";

interface HistoryViewProps {
  readonly locale: Locale;
}

export function HistoryView({ locale }: HistoryViewProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const [typed, setTyped] = useState<HistoryFilters>(NO_FILTERS);
  const [applied, setApplied] = useState<HistoryFilters>(NO_FILTERS);

  const history = useInfiniteQuery({
    queryKey: ["history", applied],
    queryFn: ({ pageParam }) => requestJson<ItemPage>("GET", historyPath(applied, pageParam)),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplied({ ...typed });
  }

  const rows = history.data?.pages.flatMap((page) => page.data) ?? [];

  return (
    <div className="mx-auto max-w-[760px] space-y-4 p-4">
      <h1 className="text-[20px] font-semibold">{t("history.title")}</h1>
      <form onSubmit={apply} role="search" className="grid gap-3 sm:grid-cols-4">
        <label className="text-[13px] font-medium sm:col-span-2">
          {t("history.search")}
          <input className={INPUT} value={typed.q} onChange={(e) => setTyped({ ...typed, q: e.target.value })} />
        </label>
        <label className="text-[13px] font-medium">
          {t("history.niche")}
          <input className={INPUT} value={typed.niche} onChange={(e) => setTyped({ ...typed, niche: e.target.value })} />
        </label>
        <label className="text-[13px] font-medium">
          {t("history.source")}
          <input className={INPUT} value={typed.source} onChange={(e) => setTyped({ ...typed, source: e.target.value })} />
        </label>
        <button
          type="submit"
          className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text sm:col-span-4 sm:justify-self-start"
        >
          {t("history.apply")}
        </button>
      </form>

      {history.isPending ? <p className="text-muted">{t("history.loading")}</p> : null}
      {history.isError ? (
        <p role="alert">
          {t("history.error")}{" "}
          <button type="button" className="underline" onClick={() => void history.refetch()}>
            {t("queue.retry")}
          </button>
        </p>
      ) : null}
      {history.isSuccess && rows.length === 0 ? <p className="text-muted">{t("history.empty")}</p> : null}

      <ul className="space-y-2">
        {rows.map((item) => (
          <HistoryRow key={item.id} item={item} locale={locale} />
        ))}
      </ul>

      {history.hasNextPage ? (
        <button
          type="button"
          className="rounded-[8px] border border-border px-4 py-2 text-[14px]"
          disabled={history.isFetchingNextPage}
          onClick={() => void history.fetchNextPage()}
        >
          {t("history.more")}
        </button>
      ) : null}
    </div>
  );
}

function HistoryRow({ item, locale }: { readonly item: ItemOut; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const last = item.last_decision;
  const state = last
    ? t("history.decided", { verdict: t(`verdict.${last.verdict}`), by: last.decided_by })
    : t("history.waiting");
  return (
    <li>
      <Link
        href={`/items/${item.id}`}
        className="block rounded-[10px] border border-border bg-surface px-4 py-3 hover:bg-surface-2"
      >
        <span className="block text-[15px] font-medium">{item.content?.title ?? "—"}</span>
        <span className="block text-[13px] text-muted">
          {item.niche ?? "—"} · {item.source} · {state}
        </span>
      </Link>
    </li>
  );
}
