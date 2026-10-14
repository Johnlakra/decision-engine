// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NicheList } from "./NicheList";

const ROWS = {
  data: [
    {
      name: "inbox",
      label: "Inbox and DMs",
      description: "a personal email or direct message",
      enabled: true,
      autonomy: "ask",
      auto_actions: [],
      source: "yaml",
      version: 3,
      laya_mode: "shadow",
    },
  ],
};

function renderList(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <NicheList locale="en" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NicheList", () => {
  it("shows each niche with its state and links to the editor", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(ROWS), { status: 200 })));

    renderList();

    const link = await screen.findByRole("link", { name: /Inbox and DMs/ });
    expect(link.getAttribute("href")).toBe("/niches/inbox");
    for (const text of ["Enabled", "Ask", "YAML file", "Version 3", "Laya mode: shadow"]) {
      expect(link.textContent).toContain(text);
    }
  });

  it("shows an error with a retry when loading fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 500 })));

    renderList();

    expect((await screen.findByRole("alert")).textContent).toBe("Could not load niches.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
