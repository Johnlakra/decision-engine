"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { ApiError, fetchActivity, fetchItem, type ItemOut } from "@/lib/api/items";
import { translate, type Locale } from "@/lib/i18n";
import { summarizeTriage } from "@/lib/item/triage";
import { DecisionPanel } from "./DecisionPanel";
import { ItemTabs, type DetailTab } from "./ItemTabs";

interface ItemDetailViewProps {
  readonly itemId: string;
  readonly locale: Locale;
}

export function ItemDetailView({ itemId, locale }: ItemDetailViewProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const [tab, setTab] = useState<DetailTab>("decision");
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => fetchItem(itemId) });

  if (item.isPending) {
    return <p className="p-6 text-muted">{t("item.loading")}</p>;
  }
  if (item.isError) {
    const notFound = item.error instanceof ApiError && item.error.status === 404;
    return (
      <div className="mx-auto max-w-[760px] p-4">
        <p role="alert">{notFound ? t("item.notFound") : t("item.error")}</p>
        <Link href="/queue" className="mt-2 inline-block underline">
          {t("item.back")}
        </Link>
      </div>
    );
  }

  const data = item.data;
  return (
    <div className="mx-auto max-w-[760px] space-y-4 p-4">
      <Link href="/queue" className="text-[13px] text-muted underline">
        {t("item.back")}
      </Link>
      <h1 className="text-[20px] font-semibold">{data.content?.title ?? "—"}</h1>
      <ItemTabs active={tab} locale={locale} onChange={setTab} />
      <section id="item-panel" role="tabpanel" aria-live="polite" aria-labelledby={`tab-${tab}`}>
        {tab === "decision" ? <DecisionPanel item={data} locale={locale} /> : null}
        {tab === "content" ? <ContentPanel item={data} locale={locale} /> : null}
        {tab === "triage" ? <TriagePanel item={data} locale={locale} /> : null}
        {tab === "activity" ? <ActivityPanel itemId={itemId} locale={locale} /> : null}
      </section>
    </div>
  );
}

function ContentPanel({ item, locale }: { readonly item: ItemOut; readonly locale: Locale }) {
  const t = (key: string) => translate(locale, key);
  const content = item.content;
  const rows: [string, string | null | undefined][] = [
    [t("item.content.summary"), content?.summary],
    [t("item.content.body"), content?.body],
    [t("item.content.sender"), content?.sender],
    [t("item.content.language"), content?.language ?? item.language],
  ];
  const link = content?.url?.startsWith("https://") ? content.url : null;
  return (
    <dl className="space-y-3 text-[14px]">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[13px] text-muted">{label}</dt>
          <dd className="whitespace-pre-line">{value || t("item.content.none")}</dd>
        </div>
      ))}
      {link ? (
        <a href={link} target="_blank" rel="noopener noreferrer" className="underline">
          {t("item.content.link")}
        </a>
      ) : null}
    </dl>
  );
}

function TriagePanel({ item, locale }: { readonly item: ItemOut; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const triage = summarizeTriage(item.triage);
  if (!triage) {
    return <p className="text-[14px] text-muted">{t("item.triage.none")}</p>;
  }
  return (
    <div className="space-y-3 text-[14px]">
      <p>
        {t("item.triage.mode")}: {triage.mode ?? "—"} · {t("item.triage.decidedBy")}:{" "}
        {triage.decidedBy ?? "—"}
        {triage.latencyMs !== null ? ` · ${t("item.triage.latency", { ms: triage.latencyMs })}` : ""}
      </p>
      <ul className="space-y-1">
        {triage.answers.map((answer) => (
          <li key={answer.question} className="rounded-[8px] bg-surface-2 px-3 py-2">
            <span className="font-medium">{answer.question}</span>: {answer.choice ?? "—"}
            {answer.confidence ? ` (${t(`queue.confidence.${answer.confidence}`)})` : ""}
            <span className="text-muted"> · {answer.source}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActivityPanel({ itemId, locale }: { readonly itemId: string; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const activity = useQuery({
    queryKey: ["item", itemId, "activity"],
    queryFn: () => fetchActivity(itemId),
  });
  if (activity.isPending) {
    return <p className="text-muted">{t("item.loading")}</p>;
  }
  if (activity.isError) {
    return <p role="alert">{t("item.error")}</p>;
  }
  if (activity.data.data.length === 0) {
    return <p className="text-[14px] text-muted">{t("item.activity.none")}</p>;
  }
  return (
    <ul className="space-y-2 text-[14px]">
      {activity.data.data.map((entry) => (
        <li key={`${entry.created_at}-${entry.action}`} className="rounded-[8px] bg-surface-2 px-3 py-2">
          <span className="font-medium">{entry.action}</span> ·{" "}
          {t("item.activity.status", { status: entry.status })}
          {entry.undone_at ? ` · ${t("item.activity.undone")}` : ""}
          <span className="block text-[12px] text-muted">
            {new Date(entry.created_at).toLocaleString(locale)}
          </span>
        </li>
      ))}
    </ul>
  );
}
