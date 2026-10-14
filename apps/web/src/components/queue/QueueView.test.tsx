// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UNDO_WINDOW_MS } from "@/lib/queue/undo";
import { QueueView } from "./QueueView";

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
});
