// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ItemDetailView } from "./ItemDetailView";

const ITEM_ID = "0192f0c2-7a52-7c1e-9d3b-1f2a3b4c5d6e";
const ITEM = {
  id: ITEM_ID,
  source: "telegram",
  status: "awaiting_approval",
  urgency: 2,
  content: { title: "Grant call closes Friday" },
  decision: {
    options: [
      { id: "A", label: "Ignore it" },
      { id: "B", label: "Apply now" },
    ],
    recommended: "B",
    rationale: "Fits your interests.",
    confidence: 0.9,
  },
};

let fetchMock: ReturnType<typeof vi.fn>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function postCalls(): [string, RequestInit][] {
  return fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "POST",
  ) as [string, RequestInit][];
}

function renderDetail(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ItemDetailView itemId={ITEM_ID} locale="en" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "POST" ? json({}) : json(ITEM),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ItemDetailView", () => {
  it("loads the item and lists the recommended option first and selected", async () => {
    renderDetail();

    await screen.findByRole("heading", { name: "Grant call closes Friday" });
    const radios = screen.getAllByRole("radio") as HTMLInputElement[];
    expect(radios.map((radio) => radio.value)).toEqual(["B", "A"]);
    expect(radios[0]?.checked).toBe(true);
    expect(screen.getByText("Fits your interests.")).toBeTruthy();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/v1/items/${ITEM_ID}`);
  });

  it("posts the approve verdict with the selected option", async () => {
    renderDetail();
    await screen.findByRole("heading", { name: "Grant call closes Friday" });

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await screen.findByRole("status");
    const calls = postCalls();
    expect(calls).toHaveLength(1);
    expect(calls[0]?.[0]).toBe(`/api/v1/items/${ITEM_ID}/decision`);
    expect(JSON.parse(String(calls[0]?.[1].body))).toEqual({ verdict: "approve", option: "B" });
  });

  it("shows the not-found message on a 404", async () => {
    fetchMock.mockImplementation(async () => json({}, 404));

    renderDetail();

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("This item was not found."),
    );
  });

  it("shows the generic error on a server failure", async () => {
    fetchMock.mockImplementation(async () => json({}, 500));

    renderDetail();

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("Could not load this item."),
    );
  });
});
