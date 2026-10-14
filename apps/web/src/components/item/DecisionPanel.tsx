"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { postDecisionBody, type DecisionBody, type ItemOut } from "@/lib/api/items";
import { translate, type Locale } from "@/lib/i18n";
import { decisionErrorKey } from "@/lib/item/decision-error";
import { buildDecisionBody, type FormVerdict } from "@/lib/item/decision-form";
import { orderedOptions, rationaleOf, recommendedIdOf } from "@/lib/queue/view";

interface DecisionPanelProps {
  readonly item: ItemOut;
  readonly locale: Locale;
}

const WAITING = "awaiting_approval";
const SECONDARY =
  "rounded-[8px] border border-border px-4 py-2 text-[14px] text-text disabled:opacity-50";
const PRIMARY =
  "rounded-[8px] bg-primary px-4 py-2 text-[14px] font-medium text-primary-text disabled:opacity-50";
const FIELD = "mt-1 w-full rounded-[8px] border border-border bg-surface p-2 text-[14px]";

export function DecisionPanel({ item, locale }: DecisionPanelProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const options = orderedOptions(item.decision);
  const [option, setOption] = useState<string | null>(recommendedIdOf(item.decision));
  const [note, setNote] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: (body: DecisionBody) => postDecisionBody(item.id, body),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["item", item.id] });
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
    },
    onError: (error) => setFormError(t(decisionErrorKey(error))),
  });

  function submit(verdict: FormVerdict) {
    setSaved(false);
    const result = buildDecisionBody({ option, note }, verdict);
    if (!result.ok) {
      setFormError(t(`item.errors.${result.error}`));
      return;
    }
    setFormError(null);
    save.mutate(result.body);
  }

  if (item.status !== WAITING) {
    const last = item.last_decision;
    return (
      <p className="text-[14px] text-muted">
        {t("item.readOnly")}
        {last ? ` ${t("item.decidedBy", { by: last.decided_by })}: ${last.verdict}.` : ""}
      </p>
    );
  }

  const rationale = rationaleOf(item.decision);
  return (
    <div className="space-y-4">
      {rationale ? <p className="text-[14px]">{rationale}</p> : null}
      <fieldset className="space-y-2">
        <legend className="text-[13px] font-medium">{t("item.option")}</legend>
        {options.map((entry) => (
          <label key={entry.id} className="flex items-center gap-2 text-[14px]">
            <input
              type="radio"
              name="option"
              value={entry.id}
              checked={option === entry.id}
              onChange={() => setOption(entry.id)}
            />
            {entry.label}
          </label>
        ))}
      </fieldset>
      <label className="block text-[13px] font-medium">
        {t("item.note")}
        <textarea className={FIELD} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      {formError ? (
        <p role="alert" className="text-[14px] text-danger">
          {formError}
        </p>
      ) : null}
      {saved ? (
        <p role="status" className="text-[14px]">
          {t("item.saved")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={PRIMARY} disabled={save.isPending} onClick={() => submit("approve")}>
          {t("item.approve")}
        </button>
        <button type="button" className={SECONDARY} disabled={save.isPending} onClick={() => submit("edit")}>
          {t("item.saveEdit")}
        </button>
        <button type="button" className={SECONDARY} disabled={save.isPending} onClick={() => submit("reject")}>
          {t("item.reject")}
        </button>
      </div>
    </div>
  );
}
