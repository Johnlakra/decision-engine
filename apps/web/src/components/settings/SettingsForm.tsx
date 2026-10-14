"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import type { components } from "@decision-engine/client";
import { requestJson } from "@/lib/api/request";
import { translate, type Locale } from "@/lib/i18n";
import {
  formFromSettings,
  formToPayload,
  MAX_PING_CAP,
  type Language,
  type SettingsForm as FormState,
  type SettingsPayload,
} from "@/lib/settings/form";

type SettingsOut = components["schemas"]["SettingsOut"];

const LANGUAGES: readonly { readonly code: Language; readonly name: string }[] = [
  { code: "en", name: "English" },
  { code: "hi", name: "हिन्दी" },
  { code: "pa", name: "ਪੰਜਾਬੀ" },
];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const CONTROL = "mt-1 w-full rounded-[8px] border border-border bg-surface p-2 text-[14px]";

interface SettingsFormProps {
  readonly locale: Locale;
}

export function SettingsForm({ locale }: SettingsFormProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => requestJson<SettingsOut>("GET", "/settings"),
  });

  if (query.isPending) {
    return <p className="p-6 text-muted">{t("settings.loading")}</p>;
  }
  if (query.isError) {
    return (
      <div className="p-6">
        <p role="alert">{t("settings.error")}</p>
        <button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
          {t("queue.retry")}
        </button>
      </div>
    );
  }
  return <SettingsEditor initial={formFromSettings(query.data)} locale={locale} />;
}

function hourOptions(): ReactNode[] {
  return HOURS.map((hour) => (
    <option key={hour} value={String(hour)}>
      {`${String(hour).padStart(2, "0")}:00`}
    </option>
  ));
}

function SettingsEditor({ initial, locale }: { readonly initial: FormState; readonly locale: Locale }) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(initial);
  const [errors, setErrors] = useState<readonly string[]>([]);
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (payload: SettingsPayload) => requestJson("PUT", "/settings", payload),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: () => setErrors([t("settings.error")]),
  });

  function submit() {
    setSaved(false);
    const result = formToPayload(form);
    if (!result.ok) {
      setErrors(result.errors.map((field) => t(`settings.field.${field}`)));
      return;
    }
    setErrors([]);
    save.mutate(result.payload);
  }

  function toggleLanguage(code: Language) {
    const languages = form.languages.includes(code)
      ? form.languages.filter((entry) => entry !== code)
      : [...form.languages, code];
    setForm({ ...form, languages });
  }

  return (
    <form
      className="mx-auto max-w-[560px] space-y-5 p-4"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <h1 className="text-[20px] font-semibold">{t("settings.title")}</h1>

      <fieldset className="grid grid-cols-2 gap-3">
        <legend className="text-[13px] font-medium">{t("settings.quiet")}</legend>
        <label className="text-[13px]">
          {t("settings.from")}
          <select className={CONTROL} value={form.quietFrom} onChange={(e) => setForm({ ...form, quietFrom: e.target.value })}>
            {hourOptions()}
          </select>
        </label>
        <label className="text-[13px]">
          {t("settings.to")}
          <select className={CONTROL} value={form.quietTo} onChange={(e) => setForm({ ...form, quietTo: e.target.value })}>
            {hourOptions()}
          </select>
        </label>
      </fieldset>

      <label className="block text-[13px] font-medium">
        {t("settings.digest")}
        <select className={CONTROL} value={form.digestHour} onChange={(e) => setForm({ ...form, digestHour: e.target.value })}>
          {hourOptions()}
        </select>
      </label>

      <label className="block text-[13px] font-medium">
        {t("settings.cap", { max: MAX_PING_CAP })}
        <input
          className={CONTROL}
          inputMode="numeric"
          value={form.pingCap}
          onChange={(e) => setForm({ ...form, pingCap: e.target.value })}
        />
      </label>

      <label className="block text-[13px] font-medium">
        {t("settings.interests")}
        <input
          className={CONTROL}
          value={form.interests}
          onChange={(e) => setForm({ ...form, interests: e.target.value })}
        />
      </label>

      <fieldset className="space-y-2">
        <legend className="text-[13px] font-medium">{t("settings.languages")}</legend>
        {LANGUAGES.map((language) => (
          <label key={language.code} className="flex items-center gap-2 text-[14px]">
            <input
              type="checkbox"
              checked={form.languages.includes(language.code)}
              onChange={() => toggleLanguage(language.code)}
            />
            {language.name}
          </label>
        ))}
      </fieldset>

      {errors.length > 0 ? (
        <div role="alert" className="text-[14px] text-danger">
          <p>{t("settings.errors")}</p>
          <ul className="list-disc pl-5">
            {errors.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {saved && errors.length === 0 ? (
        <p role="status" className="text-[14px]">
          {t("settings.saved")}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={save.isPending}
        className="rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-50"
      >
        {t("settings.save")}
      </button>
    </form>
  );
}
