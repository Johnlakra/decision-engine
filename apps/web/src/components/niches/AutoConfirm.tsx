"use client";

import { useEffect, useRef } from "react";
import { translate, type Locale } from "@/lib/i18n";

interface AutoConfirmProps {
  readonly actions: readonly string[];
  readonly locale: Locale;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/** Shown before saving `autonomy: auto`: lists the actions that will then run without asking. */
export function AutoConfirm({ actions, locale, onConfirm, onCancel }: AutoConfirmProps) {
  const t = (key: string) => translate(locale, key);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
  }, []);

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="auto-confirm-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          onCancel();
        }
      }}
    >
      <div className="w-full max-w-[420px] space-y-3 rounded-[12px] bg-surface p-4">
        <h2 id="auto-confirm-title" className="text-[16px] font-semibold">
          {t("niches.confirm.title")}
        </h2>
        {actions.length > 0 ? (
          <>
            <p className="text-[14px]">{t("niches.confirm.body")}</p>
            <ul className="list-disc pl-5 text-[14px]">
              {actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-[14px]">{t("niches.confirm.none")}</p>
        )}
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} type="button" className="rounded-[8px] border border-border px-3 py-2 text-[14px]" onClick={onCancel}>
            {t("niches.confirm.no")}
          </button>
          <button type="button" className="rounded-[8px] bg-primary px-3 py-2 text-[14px] text-primary-text" onClick={onConfirm}>
            {t("niches.confirm.yes")}
          </button>
        </div>
      </div>
    </div>
  );
}
