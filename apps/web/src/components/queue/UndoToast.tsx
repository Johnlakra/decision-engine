import { translate, type Locale } from "@/lib/i18n";

interface UndoToastProps {
  readonly label: string;
  readonly locale: Locale;
  readonly onUndo: () => void;
}

/** Shown after every queue action for the undo window (docs/UI_UX.md: "Archived · Undo"). */
export function UndoToast({ label, locale, onUndo }: UndoToastProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded-[10px] bg-text px-4 py-3 text-[14px] text-bg shadow"
    >
      <span>{label}</span>
      <button type="button" onClick={onUndo} className="font-medium underline underline-offset-4">
        {translate(locale, "queue.undo")}
      </button>
    </div>
  );
}
