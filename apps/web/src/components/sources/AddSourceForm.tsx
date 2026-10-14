"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createSource } from "@/lib/api/sources";
import { translate, type Locale } from "@/lib/i18n";
import {
  buildSourceBody,
  MAX_NAME_CHARS,
  slugFromName,
  SOURCE_TYPES,
  sourceErrorView,
  validateSource,
  type SourceDraft,
  type SourceErrorView,
  type SourceField,
  type SourceFieldErrors,
  type SourceType,
} from "@/lib/sources/form";

const CONTROL = "mt-1 w-full rounded-[8px] border border-border bg-surface p-2 text-[14px]";
const EMPTY: SourceDraft = { type: "rss", name: "", slug: "", value: "" };

interface AddSourceFormProps {
  readonly locale: Locale;
}

interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly messages: readonly string[];
  readonly children: (describedBy: string | undefined, invalid: boolean) => React.ReactNode;
}

function Field({ id, label, messages, children }: FieldProps) {
  const errorId = `${id}-error`;
  const invalid = messages.length > 0;
  return (
    <div>
      <label htmlFor={id} className="text-[14px] font-medium">
        {label}
      </label>
      {children(invalid ? errorId : undefined, invalid)}
      {invalid ? (
        <p id={errorId} className="mt-1 text-[13px] text-danger">
          {messages.join(" ")}
        </p>
      ) : null}
    </div>
  );
}

export function AddSourceForm({ locale }: AddSourceFormProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<SourceDraft>(EMPTY);
  const [slugTouched, setSlugTouched] = useState(false);
  const [local, setLocal] = useState<SourceFieldErrors>({});
  const [server, setServer] = useState<SourceErrorView | null>(null);
  const [added, setAdded] = useState(false);

  const create = useMutation({
    mutationFn: () => createSource(buildSourceBody(draft)),
    onSuccess: () => {
      setDraft(EMPTY);
      setSlugTouched(false);
      setServer(null);
      setAdded(true);
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
    onError: (error) => setServer(sourceErrorView(error)),
  });

  function change(patch: Partial<SourceDraft>) {
    setAdded(false);
    setDraft((current) => ({ ...current, ...patch }));
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setAdded(false);
    setServer(null);
    const errors = validateSource(draft);
    setLocal(errors);
    if (Object.keys(errors).length === 0) {
      create.mutate();
    }
  }

  function messages(field: SourceField): readonly string[] {
    const own = local[field];
    const remote = server?.kind === "validation" ? (server.fields[field] ?? []) : [];
    const taken = field === "slug" && server?.kind === "slugTaken" ? [t("sources.error.slugTaken")] : [];
    return [...(own === undefined ? [] : [t(own)]), ...remote, ...taken];
  }

  const isRss = draft.type === "rss";
  return (
    <form onSubmit={submit} noValidate className="space-y-3 rounded-[12px] border border-border bg-surface p-3">
      <h2 className="text-[16px] font-semibold">{t("sources.add.title")}</h2>
      <Field id="source-type" label={t("sources.field.type")} messages={messages("type")}>
        {(describedBy, invalid) => (
          <select
            id="source-type"
            className={CONTROL}
            value={draft.type}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => change({ type: event.target.value as SourceType, value: "" })}
          >
            {SOURCE_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`sources.type.${type}`)}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field id="source-name" label={t("sources.field.name")} messages={messages("name")}>
        {(describedBy, invalid) => (
          <input
            id="source-name"
            className={CONTROL}
            value={draft.name}
            maxLength={MAX_NAME_CHARS * 2}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) =>
              change({
                name: event.target.value,
                ...(slugTouched ? {} : { slug: slugFromName(event.target.value) }),
              })
            }
          />
        )}
      </Field>
      <Field id="source-slug" label={t("sources.field.slug")} messages={messages("slug")}>
        {(describedBy, invalid) => (
          <input
            id="source-slug"
            className={CONTROL}
            value={draft.slug}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => {
              setSlugTouched(true);
              change({ slug: event.target.value });
            }}
          />
        )}
      </Field>
      <Field
        id="source-value"
        label={t(isRss ? "sources.field.url" : "sources.field.query")}
        messages={messages("value")}
      >
        {(describedBy, invalid) => (
          <input
            id="source-value"
            className={CONTROL}
            value={draft.value}
            inputMode={isRss ? "url" : "text"}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            onChange={(event) => change({ value: event.target.value })}
          />
        )}
      </Field>
      {server?.kind === "admin" ? <p role="alert">{t("sources.error.admin")}</p> : null}
      {server?.kind === "other" ? <p role="alert">{t("sources.error.other")}</p> : null}
      {server?.kind === "validation" && server.general.length > 0 ? (
        <p role="alert">{server.general.join(" ")}</p>
      ) : null}
      {added ? <p role="status">{t("sources.added")}</p> : null}
      <button
        type="submit"
        disabled={create.isPending}
        className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-60"
      >
        {t("sources.add.submit")}
      </button>
      <p className="text-[13px] text-muted">{t("sources.later")}</p>
    </form>
  );
}
