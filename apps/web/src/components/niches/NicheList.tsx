"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { fetchNiches, type NicheRow } from "@/lib/api/niches";
import { translate, type Locale } from "@/lib/i18n";

interface NicheListProps {
  readonly locale: Locale;
}

export function NicheList({ locale }: NicheListProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const query = useQuery({ queryKey: ["niches"], queryFn: fetchNiches });

  if (query.isPending) {
    return <p className="p-6 text-muted">{t("niches.loading")}</p>;
  }
  if (query.isError) {
    return (
      <div className="p-6">
        <p role="alert">{t("niches.error")}</p>
        <button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
          {t("queue.retry")}
        </button>
      </div>
    );
  }
  const rows = query.data.data;
  return (
    <section className="mx-auto max-w-[760px] space-y-3 p-4">
      <h1 className="text-[20px] font-semibold">{t("niches.title")}</h1>
      {rows.length === 0 ? <p className="text-muted">{t("niches.empty")}</p> : null}
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.name}>
            <NicheCard row={row} locale={locale} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function NicheCard({ row, locale }: { readonly row: NicheRow; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  return (
    <Link
      href={`/niches/${row.name}`}
      className="block rounded-[12px] border border-border bg-surface p-3 hover:border-primary"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[16px] font-semibold">{row.label}</span>
        <span className="text-[13px] text-muted">{row.name}</span>
      </div>
      <p className="mt-1 text-[14px] text-muted">{row.description}</p>
      <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px]">
        <div>
          <dt className="sr-only">{t("niches.enabled")}</dt>
          <dd>{row.enabled ? t("niches.enabled") : t("niches.disabled")}</dd>
        </div>
        <div>
          <dt className="sr-only">{t("niches.autonomy")}</dt>
          <dd>{t(`niches.autonomy.${row.autonomy}`)}</dd>
        </div>
        <div>
          <dt className="sr-only">{t("niches.source")}</dt>
          <dd>{t(`niches.source.${row.source}`)}</dd>
        </div>
        <div>{t("niches.version", { version: row.version })}</div>
        <div>{t("niches.laya", { mode: t(`niches.laya.${row.laya_mode}`) })}</div>
      </dl>
    </Link>
  );
}
