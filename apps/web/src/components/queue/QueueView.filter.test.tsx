// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueueView } from "./QueueView";

const routerReplace = vi.fn();
let currentSearch = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
  useSearchParams: () => new URLSearchParams(currentSearch),
}));

function make(id: string, title: string, niche: string, source: string, urgency: number) {
  return {
    id,
    source,
    niche,
    urgency,
    created_at: "2026-10-01T00:00:00Z",
    content: { title },
    decision: { options: [{ id: "A", label: "Save" }], recommended: "A" },
  };
}

const PAGE = {
  data: [
    make("i1", "Alpha", "news_radar", "rss", 1),
    make("i2", "Bravo", "tech_stack", "webhook", 3),
    make("i3", "Charlie", "news_radar", "webhook", 0),
  ],
};

async function renderQueue(): Promise<void> {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <QueueView locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: /Alpha|Bravo/ });
}

beforeEach(() => {
  currentSearch = "";
  routerReplace.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(PAGE), { status: 200, headers: { "Content-Type": "application/json" } })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("QueueView filters", () => {
  it("shows only the niche named in the URL, most urgent first", async () => {
    currentSearch = "niche=news_radar";
    await renderQueue();

    expect(screen.getByRole("heading", { name: "Alpha" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "j" });
    expect(await screen.findByRole("heading", { name: "Charlie" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Bravo" })).toBeNull();
  });

  it("writes the picked chip to the URL and keeps the other chip", async () => {
    currentSearch = "source=rss";
    await renderQueue();

    fireEvent.click(screen.getByRole("button", { name: "tech_stack" }));

    expect(routerReplace).toHaveBeenCalledWith("/queue?source=rss&niche=tech_stack");
  });
});
