// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UNDO_WINDOW_MS } from "@/lib/queue/undo";
import { QueueView } from "./QueueView";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function make(id: string, title: string, urgency: number, risk = "none") {
  return {
    id,
    source: "rss",
    urgency,
    risk,
    content: { title },
    decision: {
      options: [
        { id: "A", label: "Save" },
        { id: "B", label: "Skip" },
      ],
      recommended: id === "i3" ? "B" : "A",
    },
  };
}
const PAGE = {
  data: [make("i1", "First", 0), make("i2", "Second", 1), make("i3", "Third", 0), make("i4", "Urgent one", 3), make("i5", "Scammy", 0, "scam")],
};

let fetchMock: ReturnType<typeof vi.fn>;
let statusFor: (url: string) => number;

function posts(): [string, RequestInit][] {
  return fetchMock.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "POST") as [
    string,
    RequestInit,
  ][];
}
function press(key: string): void {
  act(() => {
    fireEvent.keyDown(window, { key });
  });
}
async function passWindow(): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(UNDO_WINDOW_MS + 1_000);
  });
}
async function renderQueue(): Promise<void> {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <QueueView locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: "First" });
}

beforeEach(() => {
  statusFor = () => 200;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response("{}", { status: statusFor(url) })
      : new Response(JSON.stringify(PAGE), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("bulk mode", () => {
  it("shows no checkboxes until bulk mode is on, then only for eligible cards", async () => {
    await renderQueue();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);

    press("b");

    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
    expect(screen.queryByRole("checkbox", { name: /Urgent one/ })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: /Scammy/ })).toBeNull();
  });

  it("the header toggle enters bulk mode and Escape leaves it", async () => {
    await renderQueue();
    fireEvent.click(screen.getByRole("button", { name: "Bulk" }));
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);

    press("Escape");

    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /Approve recommended/ })).toBeNull();
  });

  it("disables bulk approve with an empty selection", async () => {
    await renderQueue();
    press("b");
    const button = screen.getByRole("button", { name: "Approve recommended (0)" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("space toggles the focused eligible card and updates the count", async () => {
    await renderQueue();
    press("b");
    press(" ");
    expect(screen.getByRole("button", { name: "Approve recommended (1)" })).toBeTruthy();
    press(" ");
    expect(screen.getByRole("button", { name: "Approve recommended (0)" })).toBeTruthy();
  });

  it("space on an ineligible focused card selects nothing", async () => {
    await renderQueue();
    press("b");
    press("j");
    press("j");
    press("j");
    press(" ");
    expect(screen.getByRole("button", { name: "Approve recommended (0)" })).toBeTruthy();
  });

  it("approves N selected items with their recommended option after the window", async () => {
    await renderQueue();
    press("b");
    for (const box of screen.getAllByRole("checkbox")) {
      fireEvent.click(box);
    }
    fireEvent.click(screen.getByRole("button", { name: "Approve recommended (3)" }));

    expect(screen.getByRole("status").textContent).toContain("Approved 3");
    expect(posts()).toHaveLength(0);
    await passWindow();

    const sent = posts().map(([url, init]) => [url, JSON.parse(String(init.body))]);
    expect(sent).toEqual([
      ["/api/v1/items/i1/decision", { verdict: "approve", option: "A" }],
      ["/api/v1/items/i2/decision", { verdict: "approve", option: "A" }],
      ["/api/v1/items/i3/decision", { verdict: "approve", option: "B" }],
    ]);
  });

  it("one Undo cancels the whole batch", async () => {
    await renderQueue();
    press("b");
    for (const box of screen.getAllByRole("checkbox")) {
      fireEvent.click(box);
    }
    fireEvent.click(screen.getByRole("button", { name: "Approve recommended (3)" }));

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await passWindow();

    expect(posts()).toHaveLength(0);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("heading", { name: "First" })).toBeTruthy();
  });

  it("a 409 on one item drops only that card with no error banner", async () => {
    statusFor = (url) => (url.includes("/i2/") ? 409 : 200);
    await renderQueue();
    press("b");
    for (const box of screen.getAllByRole("checkbox")) {
      fireEvent.click(box);
    }
    fireEvent.click(screen.getByRole("button", { name: "Approve recommended (3)" }));
    await passWindow();

    expect(posts()).toHaveLength(3);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("single-item keys still work outside bulk mode", async () => {
    await renderQueue();
    press("a");
    await passWindow();
    expect(posts()).toHaveLength(1);
  });
});
