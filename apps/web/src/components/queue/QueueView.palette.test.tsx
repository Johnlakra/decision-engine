// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UNDO_WINDOW_MS } from "@/lib/queue/undo";
import { QueueView } from "./QueueView";

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: routerPush }) }));

const FIRST_ID = "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e";
const makeItem = (id: string, title: string) => ({
  id,
  source: "telegram",
  urgency: 1,
  content: { title },
  decision: {
    options: [
      { id: "A", label: "Save" },
      { id: "B", label: "Skip" },
    ],
    recommended: "A",
    rationale: "Because.",
    confidence: 0.9,
  },
});
const PAGE = { data: [makeItem(FIRST_ID, "First item"), makeItem("0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6f", "Second one")] };

let fetchMock: ReturnType<typeof vi.fn>;

async function renderQueue(): Promise<void> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <QueueView locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: "First item" });
}

function openPalette(init: KeyboardEventInit = { key: "k", ctrlKey: true }): void {
  act(() => {
    fireEvent.keyDown(window, init);
  });
}

beforeEach(() => {
  routerPush.mockClear();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "POST"
      ? new Response("{}", { status: 200 })
      : new Response(JSON.stringify(PAGE), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("command palette", () => {
  it("opens with Ctrl+K and Cmd+K as an accessible modal dialog with a listbox", async () => {
    await renderQueue();
    openPalette();
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.getByRole("listbox")).toBeTruthy();
    expect(screen.getAllByRole("option")).toHaveLength(11);
    expect(document.activeElement).toBe(screen.getByRole("combobox"));

    act(() => {
      fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    });
    openPalette({ key: "k", metaKey: true });
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("filters as the user types and shows an empty state", async () => {
    await renderQueue();
    openPalette();
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "history" } });
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Go to History"]);
    fireEvent.change(input, { target: { value: "zzzz" } });
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByText("No matching commands")).toBeTruthy();
  });

  it("ArrowDown then Enter runs Next item and closes", async () => {
    await renderQueue();
    openPalette();
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "item" } });
    // order: Open item detail, Next item, Previous item
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1]?.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(input, { key: "Enter" });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { name: "Second one" })).toBeTruthy();
  });

  it("Escape closes and restores focus to the previously focused element", async () => {
    await renderQueue();
    const row = screen.getByRole("button", { name: "Second one" });
    row.focus();
    openPalette();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(row);
  });

  it("Approve from the palette holds the decision with undo, then sends once", async () => {
    await renderQueue();
    openPalette();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });

    expect(screen.getByRole("status").textContent).toContain("Done");
    expect(fetchMock.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toHaveLength(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UNDO_WINDOW_MS + 1_000);
    });
    const posts = fetchMock.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]?.[0]).toBe(`/api/v1/items/${FIRST_ID}/decision`);
  });

  it("Undo after a palette approve cancels the send", async () => {
    await renderQueue();
    openPalette();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(UNDO_WINDOW_MS + 1_000);
    });
    expect(fetchMock.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(false);
  });

  it("Snooze opens the snooze menu and navigation commands use the router", async () => {
    await renderQueue();
    openPalette();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "snooze" } });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    expect(screen.getByRole("menu", { name: "Snooze until" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("menuitem", { name: /Later today/ }));
    act(() => {
      fireEvent.keyDown(window, { key: "Escape" });
    });

    openPalette();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "settings" } });
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
    expect(routerPush).toHaveBeenCalledWith("/settings");
  });

  it("typing letters in the palette input does not trigger queue shortcuts", async () => {
    await renderQueue();
    openPalette();
    fireEvent.keyDown(screen.getByRole("combobox"), { key: "a" });
    expect(screen.queryByRole("status")).toBeNull();
  });
});
