// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HistoryView } from "./HistoryView";

const PAGE = {
  data: [
    {
      id: "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e",
      source: "telegram",
      niche: "inbox",
      content: { title: "Invoice from vendor" },
      last_decision: { verdict: "approve", decided_by: "human" },
    },
    {
      id: "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6f",
      source: "rss",
      niche: null,
      content: { title: "Weekly digest" },
      last_decision: null,
    },
  ],
  next_cursor: null,
};

let fetchMock: ReturnType<typeof vi.fn>;

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function renderHistory(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <HistoryView locale="en" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock = vi.fn(async () => json(PAGE));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("HistoryView", () => {
  it("renders a row per item from the first page with its state", async () => {
    renderHistory();

    await screen.findByText("Invoice from vendor");
    expect(screen.getByText("Weekly digest")).toBeTruthy();
    expect(screen.getByText("inbox · telegram · Approved by human")).toBeTruthy();
    expect(screen.getByText("— · rss · Waiting for you")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("shows the empty message for an empty page", async () => {
    fetchMock.mockImplementation(async () => json({ data: [], next_cursor: null }));

    renderHistory();

    expect(await screen.findByText("Nothing matches these filters.")).toBeTruthy();
  });

  it("requests the list with the niche filter after submitting", async () => {
    renderHistory();
    await screen.findByText("Invoice from vendor");

    fireEvent.change(screen.getByLabelText("Niche"), { target: { value: " inbox " } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));
    const url = String(fetchMock.mock.calls[1]?.[0]);
    expect(url.startsWith("/api/v1/items?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("niche")).toBe("inbox");
    expect(params.get("limit")).toBe("25");
  });
});
