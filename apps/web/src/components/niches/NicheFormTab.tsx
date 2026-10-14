"use client";

import type { ReactNode } from "react";
import { AUTONOMY_VALUES, URGENCY_VALUES, type FormField, type NicheForm } from "@/lib/niches/form";
import { translate, type Locale } from "@/lib/i18n";

const CONTROL = "mt-1 w-full rounded-[8px] border border-border bg-surface p-2 text-[14px]";

interface NicheFormTabProps {
  readonly form: NicheForm;
  readonly fieldErrors: Partial<Record<FormField, readonly string[]>>;
  readonly locale: Locale;
  readonly onChange: (field: FormField, value: string | boolean) => void;
}

function FieldErrors({ id, messages }: { readonly id: string; readonly messages?: readonly string[] }) {
  if (!messages || messages.length === 0) {
    return null;
  }
  return (
    <ul id={id} className="mt-1 list-disc pl-5 text-[13px] text-danger">
      {messages.map((message) => (
        <li key={message}>{message}</li>
      ))}
    </ul>
  );
}

function Field({ field, label, errors, children }: {
  readonly field: FormField;
  readonly label: string;
  readonly errors?: readonly string[];
  readonly children: ReactNode;
}) {
  return (
    <div className="text-[13px] font-medium">
      <label htmlFor={`niche-${field}`}>{label}</label>
      {children}
      <FieldErrors id={`err-${field}`} messages={errors} />
    </div>
  );
}

/** Basic fields. Each shows the server errors whose json_pointer names it. */
export function NicheFormTab({ form, fieldErrors, locale, onChange }: NicheFormTabProps) {
  const t = (key: string) => translate(locale, key);
  const aria = (field: FormField) => {
    const invalid = (fieldErrors[field]?.length ?? 0) > 0;
    return { "aria-invalid": invalid || undefined, "aria-describedby": invalid ? `err-${field}` : undefined };
  };

  return (
    <div className="space-y-4">
      <Field field="label" label={t("niches.field.label")} errors={fieldErrors.label}>
        <input id="niche-label" className={CONTROL} value={form.label} onChange={(e) => onChange("label", e.target.value)} {...aria("label")} />
      </Field>

      <Field field="description" label={t("niches.field.description")} errors={fieldErrors.description}>
        <textarea id="niche-description"
          className={CONTROL}
          rows={3}
          value={form.description}
          onChange={(e) => onChange("description", e.target.value)}
          {...aria("description")}
        />
      </Field>

      <Field field="autonomy" label={t("niches.field.autonomy")} errors={fieldErrors.autonomy}>
        <select id="niche-autonomy" className={CONTROL} value={form.autonomy} onChange={(e) => onChange("autonomy", e.target.value)} {...aria("autonomy")}>
          {AUTONOMY_VALUES.map((value) => (
            <option key={value} value={value}>
              {t(`niches.autonomy.${value}`)}
            </option>
          ))}
        </select>
      </Field>

      <Field field="actions" label={t("niches.field.actions")} errors={fieldErrors.actions}>
        <textarea id="niche-actions" className={CONTROL} rows={4} value={form.actions} onChange={(e) => onChange("actions", e.target.value)} {...aria("actions")} />
      </Field>

      <Field field="autoActions" label={t("niches.field.autoActions")} errors={fieldErrors.autoActions}>
        <textarea id="niche-autoActions"
          className={CONTROL}
          rows={3}
          value={form.autoActions}
          onChange={(e) => onChange("autoActions", e.target.value)}
          {...aria("autoActions")}
        />
      </Field>

      <fieldset className="space-y-2">
        <legend className="text-[13px] font-medium">{t("niches.field.notify")}</legend>
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={form.urgentPing} onChange={(e) => onChange("urgentPing", e.target.checked)} />
          {t("niches.field.urgentPing")}
        </label>
        <FieldErrors id="err-urgentPing" messages={fieldErrors.urgentPing} />
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={form.digest} onChange={(e) => onChange("digest", e.target.checked)} />
          {t("niches.field.digest")}
        </label>
        <FieldErrors id="err-digest" messages={fieldErrors.digest} />
        <Field field="minUrgencyForPing" label={t("niches.field.minUrgencyForPing")} errors={fieldErrors.minUrgencyForPing}>
          <select
            id="niche-minUrgencyForPing"
            className={CONTROL}
            value={form.minUrgencyForPing}
            onChange={(e) => onChange("minUrgencyForPing", e.target.value)}
            {...aria("minUrgencyForPing")}
          >
            {URGENCY_VALUES.map((value) => (
              <option key={value} value={value}>
                {t(`niches.urgency.${value}`)}
              </option>
            ))}
          </select>
        </Field>
      </fieldset>
    </div>
  );
}
