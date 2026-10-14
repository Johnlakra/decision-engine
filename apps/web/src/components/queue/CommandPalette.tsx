"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { translate, type Locale } from "@/lib/i18n";
import { COMMANDS, filterCommands, type PaletteCommandId } from "@/lib/queue/commands";

interface CommandPaletteProps {
  readonly locale: Locale;
  readonly onRun: (id: PaletteCommandId) => void;
}

const LIST_ID = "command-palette-list";

function isOpenShortcut(event: KeyboardEvent): boolean {
  return (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
}

/**
 * Cmd+K (Ctrl+K) palette. It only opens from the shortcut, so typing in other fields never opens it.
 * Focus returns to the previous element before a command runs, so a command that moves focus
 * (the snooze menu) still wins.
 */
export function CommandPalette({ locale, onRun }: CommandPaletteProps) {
  const t = (key: string) => translate(locale, key);
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const returnFocus = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(
    () => filterCommands(COMMANDS, query, (command) => translate(locale, command.labelKey)),
    [locale, query],
  );
  const activeIndex = Math.min(active, Math.max(results.length - 1, 0));

  const close = useCallback(() => {
    setIsOpen(false);
    returnFocus.current?.focus();
    returnFocus.current = null;
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (!isOpenShortcut(event)) {
        return;
      }
      event.preventDefault();
      if (isOpen) {
        close();
        return;
      }
      returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setQuery("");
      setActive(0);
      setIsOpen(true);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [close, isOpen]);

  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus();
    }
  }, [isOpen]);

  if (!isOpen) {
    return null;
  }

  const run = (id: PaletteCommandId) => {
    close();
    onRun(id);
  };

  const onInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      const count = results.length;
      setActive(count === 0 ? 0 : (activeIndex + step + count) % count);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const chosen = results[activeIndex];
      if (chosen) {
        run(chosen.id);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "Tab") {
      event.preventDefault();
    }
  };

  const activeId = results[activeIndex] ? `palette-opt-${results[activeIndex].id}` : undefined;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[15vh]" onMouseDown={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t("palette.title")}
        onMouseDown={(event) => event.stopPropagation()}
        className="w-[min(520px,92vw)] rounded-[12px] border border-border bg-surface p-2 shadow"
      >
        <input
          ref={inputRef}
          role="combobox"
          aria-expanded="true"
          aria-controls={LIST_ID}
          aria-activedescendant={activeId}
          aria-autocomplete="list"
          aria-label={t("palette.placeholder")}
          placeholder={t("palette.placeholder")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActive(0);
          }}
          onKeyDown={onInputKeyDown}
          className="w-full rounded-[8px] border border-border bg-surface px-3 py-2 text-[14px]"
        />
        <ul id={LIST_ID} role="listbox" aria-label={t("palette.title")} className="mt-2 max-h-[50vh] overflow-auto">
          {results.map((command, index) => (
            <li
              key={command.id}
              id={`palette-opt-${command.id}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => setActive(index)}
              onClick={() => run(command.id)}
              className={`cursor-pointer rounded-[8px] px-3 py-2 text-[14px] ${
                index === activeIndex ? "bg-surface-2" : ""
              }`}
            >
              {t(command.labelKey)}
            </li>
          ))}
        </ul>
        {results.length === 0 ? <p className="px-3 py-2 text-[14px] text-muted">{t("palette.empty")}</p> : null}
      </div>
    </div>
  );
}
