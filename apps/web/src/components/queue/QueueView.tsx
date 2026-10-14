"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPendingItems, postDecisionBody, type ItemOut } from "@/lib/api/items";
import { translate, type Locale } from "@/lib/i18n";
import { queueActionForKey, type QueueAction } from "@/lib/queue/keys";
import {
  cancelDecision,
  dueDecisions,
  scheduleDecision,
  type PendingDecision,
  type Verdict,
} from "@/lib/queue/undo";
import { moveIndex, orderedOptions } from "@/lib/queue/view";
import { QueueCard } from "./QueueCard";
import { UndoToast } from "./UndoToast";

const QUEUE_KEY = ["queue", "pending"] as const;
const FLUSH_INTERVAL_MS = 500;
const REFRESH_INTERVAL_MS = 30_000;
const URGENT_FROM = 2;

interface QueueViewProps {
  readonly locale: Locale;
}

/** Keys must not fire while the user is typing in a field. */
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function QueueView({ locale }: QueueViewProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: fetchPendingItems,
    refetchInterval: REFRESH_INTERVAL_MS,
  });

  const [pending, setPending] = useState<PendingDecision[]>([]);
  const pendingRef = useRef<PendingDecision[]>([]);
  const inFlight = useRef(new Set<string>());
  const [focus, setFocus] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  const items: ItemOut[] = (query.data?.data ?? []).filter(
    (item) => !pending.some((entry) => entry.itemId === item.id),
  );
  const safeFocus = items.length === 0 ? 0 : Math.min(focus, items.length - 1);
  const focused = items[safeFocus];
  const latest = pending[pending.length - 1];
  const urgentCount = items.filter((item) => (item.urgency ?? 0) >= URGENT_FROM).length;

  const holdDecision = useCallback((itemId: string, verdict: Verdict, option?: string) => {
    setFailed(false);
    pendingRef.current = scheduleDecision(pendingRef.current, itemId, verdict, Date.now(), option);
    setPending(pendingRef.current);
  }, []);

  const undo = useCallback((itemId: string) => {
    pendingRef.current = cancelDecision(pendingRef.current, itemId);
    setPending(pendingRef.current);
  }, []);

  // Send each decision once its undo window has closed. The in-flight set stops a second send.
  useEffect(() => {
    const timer = setInterval(() => {
      for (const due of dueDecisions(pendingRef.current, Date.now())) {
        if (inFlight.current.has(due.itemId)) {
          continue;
        }
        inFlight.current.add(due.itemId);
        pendingRef.current = cancelDecision(pendingRef.current, due.itemId);
        setPending(pendingRef.current);
        postDecisionBody(
          due.itemId,
          due.option ? { verdict: due.verdict, option: due.option } : { verdict: due.verdict },
        )
          .catch(() => setFailed(true))
          .finally(() => {
            inFlight.current.delete(due.itemId);
            void queryClient.invalidateQueries({ queryKey: QUEUE_KEY });
          });
      }
    }, FLUSH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [queryClient]);

  const runAction = useCallback(
    (action: QueueAction) => {
      if (action.type === "help") {
        setHelpOpen((open) => !open);
        return;
      }
      if (!focused) {
        return;
      }
      switch (action.type) {
        case "approve":
          holdDecision(focused.id, "approve");
          return;
        case "reject":
          holdDecision(focused.id, "reject");
          return;
        case "choose": {
          const option = orderedOptions(focused.decision)[action.index];
          if (option) {
            holdDecision(focused.id, "approve", option.id);
          }
          return;
        }
        case "next":
          setFocus(moveIndex(safeFocus, 1, items.length));
          return;
        case "previous":
          setFocus(moveIndex(safeFocus, -1, items.length));
          return;
        case "open": {
          const url = focused.content?.url;
          if (url?.startsWith("https://")) {
            window.open(url, "_blank", "noopener,noreferrer");
          }
          return;
        }
        case "snooze":
        case "edit":
          // Not in this slice: snooze needs a time picker and edit needs the item detail view.
          return;
      }
    },
    [focused, holdDecision, items.length, safeFocus],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const action = queueActionForKey(event.key);
      if (action) {
        event.preventDefault();
        runAction(action);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [runAction]);

  if (query.isPending) {
    return <p className="p-6 text-muted">{t("queue.loading")}</p>;
  }
  if (query.isError) {
    return (
      <div className="p-6">
        <p role="alert">{t("queue.error")}</p>
        <button type="button" className="mt-2 underline" onClick={() => void query.refetch()}>
          {t("queue.retry")}
        </button>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[760px] p-4">
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-[20px] font-semibold">{t("queue.title")}</h1>
        <p className="text-[14px] text-muted">
          {t("queue.count", { count: items.length })}
          {urgentCount > 0 ? ` · ${t("queue.urgent", { count: urgentCount })}` : ""}
        </p>
      </header>

      {failed ? (
        <p role="alert" className="mt-3 text-[14px] text-danger">
          {t("queue.failed")}
        </p>
      ) : null}

      {focused ? (
        <div className="mt-4 space-y-3">
          <QueueCard
            item={focused}
            locale={locale}
            disabled={false}
            onChoose={(optionId) => holdDecision(focused.id, "approve", optionId)}
            onReject={() => holdDecision(focused.id, "reject")}
          />
          <ul className="space-y-1" aria-label={t("queue.title")}>
            {items.map((item, index) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => setFocus(index)}
                  aria-current={index === safeFocus ? "true" : undefined}
                  className="w-full rounded-[8px] px-3 py-2 text-left text-[14px] hover:bg-surface-2"
                >
                  {item.content?.title ?? "—"}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-8 text-center text-muted">{t("queue.empty")}</p>
      )}

      {helpOpen ? (
        <p className="mt-6 rounded-[8px] border border-border p-3 text-[13px]">{t("queue.keys")}</p>
      ) : null}

      {latest ? (
        <UndoToast label={t("queue.done")} locale={locale} onUndo={() => undo(latest.itemId)} />
      ) : null}
    </div>
  );
}
