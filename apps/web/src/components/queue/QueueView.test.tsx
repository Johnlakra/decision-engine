// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UNDO_WINDOW_MS } from "@/lib/queue/undo";
import { QueueView } from "./QueueView";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

const ITEM_ID = "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e";
const PAGE = {
  data: [
    {
      id: ITEM_ID,
      source: "telegram",
      urgency: 2,
      content: { title: "Free credits for builders" },
      decision: {
        options: [
          { id: "A", label: "Save and act" },
          { id: "B", label: "Not interested" },
        ],
        recommended: "A",
        rationale: "Matches your interests.",
        confidence: 0.9,
      },
    },
  ],
};

let fetchMock: ReturnType<typeof vi.fn>;

function decisionCalls(): [string, RequestInit][] {
  return fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "POST",
  ) as [string, RequestInit][];
}

async function renderQueue(): Promise<void> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QueueView locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: "Free credits for builders" });
}

function press(key: string): void {
  act(() => {
    fireEvent.keyDown(window, { key });
  });
}

async function passUndoWindow(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(UNDO_WINDOW_MS + 1_000);
  });
}

beforeEach(() => {
  routerPush.mockClear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response("{}", { status: 200 })
      : new Response(JSON.stringify(PAGE), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("QueueView keyboard flow", () => {
  it("holds an approval for the undo window and then sends it once", async () => {
    await renderQueue();

    press("a");
    expect(screen.getByRole("status").textContent).toContain("Done");
    await passUndoWindow();

    const calls = decisionCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0]?.[0]).toBe(`/api/v1/items/${ITEM_ID}/decision`);
    expect(JSON.parse(String(calls[0]?.[1].body))).toEqual({ verdict: "approve" });
  });

  it("undo cancels the held decision so nothing is sent", async () => {
    await renderQueue();

    press("r");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    });
    await passUndoWindow();

    expect(decisionCalls()).toHaveLength(0);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("heading", { name: "Free credits for builders" })).toBeTruthy();
  });

  it("number keys send the chosen option, not the recommendation", async () => {
    await renderQueue();

    press("2");
    await passUndoWindow();

    const calls = decisionCalls();
    expect(JSON.parse(String(calls[0]?.[1].body))).toEqual({ verdict: "approve", option: "B" });
  });

  it("s then 1 holds a snooze and posts snooze with an ISO UTC snooze_until", async () => {
    await renderQueue();
    const before = Date.now();

    press("s");
    expect(screen.getByRole("menu", { name: "Snooze until" })).toBeTruthy();
    press("1");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Snoozed");
    await passUndoWindow();

    const calls = decisionCalls();
    expect(calls).toHaveLength(1);
    const body = JSON.parse(String(calls[0]?.[1].body)) as { verdict: string; snooze_until: string };
    expect(body.verdict).toBe("snooze");
    expect(body.snooze_until).toMatch(/Z$/);
    const THREE_HOURS = 3 * 60 * 60 * 1000;
    expect(new Date(body.snooze_until).getTime() - before).toBeGreaterThanOrEqual(THREE_HOURS);
  });

  it("key 3 inside the menu picks next week, a Monday 03:30 UTC", async () => {
    await renderQueue();

    press("s");
    press("3");
    await passUndoWindow();

    const body = JSON.parse(String(decisionCalls()[0]?.[1].body)) as { snooze_until: string };
    const until = new Date(body.snooze_until);
    expect(until.getUTCDay()).toBe(1);
    expect(until.toISOString().slice(11)).toBe("03:30:00.000Z");
  });

  it("Escape closes the snooze menu without holding anything", async () => {
    await renderQueue();

    press("s");
    press("Escape");
    await passUndoWindow();

    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(decisionCalls()).toHaveLength(0);
  });

  it("undo cancels a held snooze so nothing is sent", async () => {
    await renderQueue();

    press("s");
    press("2");
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    });
    await passUndoWindow();

    expect(decisionCalls()).toHaveLength(0);
  });

  it("menu keys do not approve or choose options while the menu is open", async () => {
    await renderQueue();

    press("s");
    press("a");
    await passUndoWindow();

    expect(decisionCalls()).toHaveLength(0);
  });

  it("e navigates to the item detail page", async () => {
    await renderQueue();

    press("e");

    expect(routerPush).toHaveBeenCalledWith(`/items/${ITEM_ID}`);
    expect(decisionCalls()).toHaveLength(0);
  });

  it("a 409 on send removes the card quietly with no error banner", async () => {
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? new Response("{}", { status: 409 })
        : new Response(JSON.stringify(PAGE), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    await renderQueue();

    press("a");
    await passUndoWindow();

    expect(screen.queryByRole("alert")).toBeNull();
  });
});
