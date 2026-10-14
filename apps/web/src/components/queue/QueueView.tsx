"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { decisionErrorKey } from "@/lib/item/decision-error";
import { fetchPendingItems, postDecisionBody, type DecisionBody, type ItemOut } from "@/lib/api/items";
import { translate, type Locale } from "@/lib/i18n";
import { buildBulkBatch, isBulkEligible } from "@/lib/queue/bulk";
import { queueActionForKey, type QueueAction } from "@/lib/queue/keys";
import {
  cancelBatch,
  cancelDecision,
  dueDecisions,
  scheduleDecision,
  scheduleMany,
  type PendingDecision,
  type Verdict,
} from "@/lib/queue/undo";
import { SNOOZE_KEYS, snoozePresets, type SnoozePresetKey } from "@/lib/queue/snooze";
import { moveIndex, orderedOptions } from "@/lib/queue/view";
import { CommandPalette } from "./CommandPalette";
import type { PaletteCommandId } from "@/lib/queue/commands";
import { BulkBar } from "./BulkBar";
import { QueueCard } from "./QueueCard";
import { SnoozeMenu } from "./SnoozeMenu";
import { UndoToast } from "./UndoToast";

const QUEUE_KEY = ["queue", "pending"] as const;
const FLUSH_INTERVAL_MS = 500;
const REFRESH_INTERVAL_MS = 30_000;
const URGENT_FROM = 2;
const MAX_CONCURRENT_SENDS = 3;
const ALREADY_HANDLED_KEY = "item.errors.alreadyHandled";

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

const PALETTE_ROUTES: Readonly<Partial<Record<PaletteCommandId, string>>> = {
  goQueue: "/queue",
  goHistory: "/history",
  goSettings: "/settings",
};

const PALETTE_ACTIONS: Readonly<Partial<Record<PaletteCommandId, QueueAction>>> = {
  approve: { type: "approve" },
  reject: { type: "reject" },
  snooze: { type: "snooze" },
  open: { type: "edit" },
  bulk: { type: "bulk" },
  next: { type: "next" },
  previous: { type: "previous" },
  help: { type: "help" },
};

function decisionBody(due: PendingDecision): DecisionBody {
  if (due.verdict === "snooze") {
    return { verdict: "snooze", snooze_until: due.snoozeUntil };
  }
  return due.option ? { verdict: due.verdict, option: due.option } : { verdict: due.verdict };
}

export function QueueView({ locale }: QueueViewProps) {
  const t = (key: string, values?: Record<string, string | number>) => translate(locale, key, values);
  const queryClient = useQueryClient();
  const router = useRouter();
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
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [bulkMode, setBulkMode] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());

  const items: ItemOut[] = (query.data?.data ?? []).filter(
    (item) => !pending.some((entry) => entry.itemId === item.id),
  );
  const safeFocus = items.length === 0 ? 0 : Math.min(focus, items.length - 1);
  const focused = items[safeFocus];
  const latest = pending[pending.length - 1];
  const toastLabel = (entry: PendingDecision): string => {
    if (entry.batchId) {
      const count = pending.filter((held) => held.batchId === entry.batchId).length;
      return t("queue.bulk.done", { count });
    }
    return t(entry.verdict === "snooze" ? "queue.snoozed" : "queue.done");
  };
  const urgentCount = items.filter((item) => (item.urgency ?? 0) >= URGENT_FROM).length;

  const holdDecision = useCallback(
    (itemId: string, verdict: Verdict, option?: string, snoozeUntil?: string) => {
      setFailed(false);
      pendingRef.current = scheduleDecision(
        pendingRef.current,
        itemId,
        verdict,
        Date.now(),
        option,
        snoozeUntil,
      );
      setPending(pendingRef.current);
    },
    [],
  );

  const pickSnooze = useCallback(
    (preset: SnoozePresetKey) => {
      setSnoozeOpen(false);
      if (focused) {
        holdDecision(focused.id, "snooze", undefined, snoozePresets(new Date())[preset]);
      }
    },
    [focused, holdDecision],
  );

  const undo = useCallback((entry: PendingDecision) => {
    pendingRef.current = entry.batchId
      ? cancelBatch(pendingRef.current, entry.batchId)
      : cancelDecision(pendingRef.current, entry.itemId);
    setPending(pendingRef.current);
  }, []);

  const exitBulk = useCallback(() => {
    setBulkMode(false);
    setSelected(new Set());
  }, []);

  const toggleSelected = useCallback((itemId: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (!next.delete(itemId)) {
        next.add(itemId);
      }
      return next;
    });
  }, []);

  const approveSelected = useCallback(() => {
    const batch = buildBulkBatch(items, selected);
    if (batch.length === 0) {
      return;
    }
    setFailed(false);
    pendingRef.current = scheduleMany(pendingRef.current, batch, Date.now(), crypto.randomUUID());
    setPending(pendingRef.current);
    exitBulk();
  }, [exitBulk, items, selected]);

  // Send each decision once its undo window has closed. The in-flight set stops a second send.
  useEffect(() => {
    const timer = setInterval(() => {
      for (const due of dueDecisions(pendingRef.current, Date.now())) {
        if (inFlight.current.has(due.itemId) || inFlight.current.size >= MAX_CONCURRENT_SENDS) {
          continue;
        }
        inFlight.current.add(due.itemId);
        pendingRef.current = cancelDecision(pendingRef.current, due.itemId);
        setPending(pendingRef.current);
        postDecisionBody(due.itemId, decisionBody(due))
          .catch((error: unknown) => {
            // 409: another client already handled the item. Drop the card quietly (ADR 0007).
            if (decisionErrorKey(error) !== ALREADY_HANDLED_KEY) {
              setFailed(true);
            }
          })
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
      if (action.type === "bulk") {
        if (bulkMode) {
          exitBulk();
        } else {
          setBulkMode(true);
        }
        return;
      }
      if (action.type === "exitBulk") {
        exitBulk();
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
        case "select":
          if (bulkMode && isBulkEligible(focused)) {
            toggleSelected(focused.id);
          }
          return;
        case "snooze":
          setSnoozeOpen(true);
          return;
        case "edit":
          router.push(`/items/${focused.id}`);
          return;
      }
    },
    [bulkMode, exitBulk, focused, holdDecision, items.length, router, safeFocus, toggleSelected],
  );

  const runPaletteCommand = useCallback(
    (id: PaletteCommandId) => {
      const route = PALETTE_ROUTES[id];
      if (route) {
        router.push(route);
        return;
      }
      const action = PALETTE_ACTIONS[id];
      if (action) {
        runAction(action);
      }
    },
    [router, runAction],
  );

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      if (snoozeOpen) {
        event.preventDefault();
        const preset = SNOOZE_KEYS[event.key];
        if (preset) {
          pickSnooze(preset);
        } else if (event.key === "Escape") {
          setSnoozeOpen(false);
        }
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
  }, [pickSnooze, runAction, snoozeOpen]);

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
      <CommandPalette locale={locale} onRun={runPaletteCommand} />
      <header className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-[20px] font-semibold">{t("queue.title")}</h1>
        <p className="text-[14px] text-muted">
          {t("queue.count", { count: items.length })}
          {urgentCount > 0 ? ` · ${t("queue.urgent", { count: urgentCount })}` : ""}
        </p>
        <button
          type="button"
          aria-pressed={bulkMode}
          aria-keyshortcuts="b"
          onClick={() => (bulkMode ? exitBulk() : setBulkMode(true))}
          className="ml-auto rounded-[8px] border border-border px-3 py-1 text-[13px]"
        >
          {t("queue.bulk.toggle")}
        </button>
      </header>

      {bulkMode ? (
        <BulkBar locale={locale} count={buildBulkBatch(items, selected).length} onApprove={approveSelected} onExit={exitBulk} />
      ) : null}

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
              <li key={item.id} className="flex items-center gap-2">
                {bulkMode && isBulkEligible(item) ? (
                  <input
                    type="checkbox"
                    checked={selected.has(item.id)}
                    onChange={() => toggleSelected(item.id)}
                    aria-label={t("queue.bulk.select", { title: item.content?.title ?? "—" })}
                    className="h-4 w-4 shrink-0"
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => setFocus(index)}
                  aria-current={index === safeFocus ? "true" : undefined}
                  className="min-w-0 flex-1 rounded-[8px] px-3 py-2 text-left text-[14px] hover:bg-surface-2"
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

      {snoozeOpen ? (
        <SnoozeMenu locale={locale} onPick={pickSnooze} onClose={() => setSnoozeOpen(false)} />
      ) : null}

      {latest ? (
        <UndoToast
          label={toastLabel(latest)}
          locale={locale}
          onUndo={() => undo(latest)}
        />
      ) : null}
    </div>
  );
}
