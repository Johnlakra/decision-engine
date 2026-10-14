// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Insights } from "./Insights";

const STATS = {
  date: "2026-10-14",
  items_in: 42,
  decided: 9,
  auto_handled: 3,
  discarded: 20,
  by_status: { awaiting_approval: 6 },
  by_niche: { news_radar: 30, unassigned: 12 },
  laya_mode: "shadow",
  laya_agreement: 0.87,
  llm: [
    { provider: "gemini", requests_used: 120, requests_limit: 500, tokens_used: 84000, tokens_limit: null },
    { provider: "groq", requests_used: 90, requests_limit: 100, tokens_used: 5, tokens_limit: null },
  ],
};

function renderInsights(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Insights locale="en" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Insights", () => {
  it("shows today's counts, budgets with text labels, niches and Laya mode", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(STATS), { status: 200 })));

    renderInsights();

    expect(await screen.findByText("Items in")).toBeTruthy();
    for (const label of ["Items in", "Decided", "Auto-handled", "Discarded"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.getByText("120 of 500 requests used")).toBeTruthy();
    expect(screen.getByText("90 of 100 requests used")).toBeTruthy();
    expect(screen.getByText("Near limit")).toBeTruthy();
    const bars = screen.getAllByRole("progressbar");
    expect(bars.map((bar) => bar.getAttribute("aria-valuenow"))).toEqual(["24", "90"]);
    expect(screen.getByText("news_radar")).toBeTruthy();
    expect(screen.getByText("Laya mode: shadow")).toBeTruthy();
  });

  it("never renders Laya agreement or time saved", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(STATS), { status: 200 })));

    renderInsights();
    await screen.findByText("Items in");

    expect(document.body.textContent).not.toMatch(/87|agreement|time saved/i);
  });

  it("shows an error with retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));

    renderInsights();

    expect((await screen.findByRole("alert")).textContent).toBe("Could not load insights.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
