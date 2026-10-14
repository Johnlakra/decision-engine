"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiError, fetchNiche, saveNiche, type NicheDetail } from "@/lib/api/niches";
import { translate, type Locale } from "@/lib/i18n";
import { saveErrorView, type SaveErrorView } from "@/lib/niches/errors";
import { applyFormField, formFromConfig, type FormField } from "@/lib/niches/form";
import { parseNicheYaml, stringifyNiche, type NicheConfig, type YamlParseResult } from "@/lib/niches/yaml";
import { AutoConfirm } from "./AutoConfirm";
import { NicheFormTab } from "./NicheFormTab";
import { NicheYamlTab } from "./NicheYamlTab";

const SYNTAX_DEBOUNCE_MS = 300;

type Tab = "basic" | "yaml";

interface NicheEditorProps {
  readonly name: string;
  readonly locale: Locale;
}

export function NicheEditor({ name, locale }: NicheEditorProps) {
  const t = (key: string) => translate(locale, key);
  const query = useQuery({ queryKey: ["niche", name], queryFn: () => fetchNiche(name) });

  if (query.isPending) {
    return <p className="p-6 text-muted">{t("niches.detail.loading")}</p>;
  }
  if (query.isError) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="p-6">
        <p role="alert">{t(missing ? "niches.detail.notFound" : "niches.detail.error")}</p>
        <Link href="/niches" className="mt-2 inline-block underline">
          {t("niches.back")}
        </Link>
      </div>
    );
  }
  return <EditorBody key={query.data.version} detail={query.data} locale={locale} />;
}

function ErrorBanner({ view, locale }: { readonly view: SaveErrorView | null; readonly locale: Locale }) {
  if (view === null) {
    return null;
  }
  const t = (key: string) => translate(locale, key);
  if (view.kind === "admin") {
    return <p role="alert" className="text-[14px] text-danger">{t("niches.errors.admin")}</p>;
  }
  if (view.kind === "other") {
    return <p role="alert" className="text-[14px] text-danger">{t("niches.errors.other")}</p>;
  }
  return <p role="alert" className="text-[14px] text-danger">{t("niches.errors.heading")}</p>;
}

function EditorBody({ detail, locale }: { readonly detail: NicheDetail; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("basic");
  const [config, setConfig] = useState<NicheConfig>(detail.config);
  const [yamlText, setYamlText] = useState(detail.yaml);
  const [syntax, setSyntax] = useState<YamlParseResult>({ ok: true, value: detail.config });
  const [errorView, setErrorView] = useState<SaveErrorView | null>(null);
  const [savedVersion, setSavedVersion] = useState<number | null>(null);
  const [confirming, setConfirming] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
    },
    [],
  );

  const save = useMutation({
    mutationFn: (body: NicheConfig) => saveNiche(detail.name, body),
    onSuccess: (result) => {
      setErrorView(null);
      setSavedVersion(result.version);
      void queryClient.invalidateQueries({ queryKey: ["niches"] });
      queryClient.setQueryData(["niche", detail.name], result);
    },
    onError: (error) => {
      setSavedVersion(null);
      setErrorView(saveErrorView(error));
    },
  });

  function changeField(field: FormField, value: string | boolean) {
    const next = applyFormField(config, field, value);
    setConfig(next);
    setYamlText(stringifyNiche(next));
    setSyntax({ ok: true, value: next });
    setSavedVersion(null);
  }

  function changeYaml(text: string) {
    setYamlText(text);
    setSavedVersion(null);
    if (timer.current !== null) {
      clearTimeout(timer.current);
    }
    timer.current = setTimeout(() => {
      const result = parseNicheYaml(text);
      setSyntax(result);
      if (result.ok) {
        setConfig(result.value);
      }
    }, SYNTAX_DEBOUNCE_MS);
  }

  function submit() {
    // Parse now, so a save right after typing never sends an older config.
    const current = tab === "yaml" ? parseNicheYaml(yamlText) : syntax;
    if (!current.ok) {
      setSyntax(current);
      return;
    }
    setConfig(current.value);
    if (current.value.autonomy === "auto") {
      setConfirming(true);
      return;
    }
    save.mutate(current.value);
  }

  const autoActions = Array.isArray(config.auto_actions)
    ? config.auto_actions.filter((entry): entry is string => typeof entry === "string")
    : [];
  const fieldErrors = errorView?.kind === "validation" ? errorView.fields : {};
  const yamlErrors = errorView?.kind === "validation" ? errorView.all : [];
  const generalErrors = errorView?.kind === "validation" ? errorView.general : [];

  return (
    <form
      className="mx-auto max-w-[640px] space-y-4 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Link href="/niches" className="text-[13px] underline">
        {t("niches.back")}
      </Link>
      <h1 className="text-[20px] font-semibold">
        {typeof config.label === "string" && config.label !== "" ? config.label : detail.name}
        <span className="ml-2 text-[13px] font-normal text-muted">
          {t(`niches.source.${detail.source}`)} · {t("niches.version", { version: detail.version })}
        </span>
      </h1>

      <div role="tablist" aria-label={t("niches.tabs.label")} className="flex gap-2 border-b border-border">
        {(["basic", "yaml"] as const).map((id) => (
          <button
            key={id}
            id={`niche-tab-${id}`}
            role="tab"
            type="button"
            aria-selected={tab === id}
            aria-controls="niche-panel"
            tabIndex={tab === id ? 0 : -1}
            onClick={() => setTab(id)}
            className={tab === id ? "border-b-2 border-primary px-3 py-2 font-semibold" : "px-3 py-2 text-muted"}
          >
            {t(`niches.tabs.${id}`)}
          </button>
        ))}
      </div>

      <ErrorBanner view={errorView} locale={locale} />
      {tab === "basic" && generalErrors.length > 0 ? (
        <ul className="list-disc pl-5 text-[13px] text-danger">
          {generalErrors.map((error) => (
            <li key={`${error.pointer}:${error.message}`}>
              <code>{error.pointer === "" ? t("niches.errors.root") : error.pointer}</code> {error.message}
            </li>
          ))}
        </ul>
      ) : null}

      <div id="niche-panel" role="tabpanel" aria-labelledby={`niche-tab-${tab}`}>
        {tab === "basic" ? (
          <NicheFormTab form={formFromConfig(config)} fieldErrors={fieldErrors} locale={locale} onChange={changeField} />
        ) : (
          <NicheYamlTab text={yamlText} syntax={syntax} serverErrors={yamlErrors} locale={locale} onChange={changeYaml} />
        )}
      </div>

      {savedVersion !== null ? (
        <p role="status" className="text-[14px]">
          {t("niches.saved", { version: savedVersion })}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={save.isPending || !syntax.ok}
        className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-50"
      >
        {save.isPending ? t("niches.saving") : t("niches.save")}
      </button>

      {confirming ? (
        <AutoConfirm
          actions={autoActions}
          locale={locale}
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false);
            save.mutate(config);
          }}
        />
      ) : null}
    </form>
  );
}
