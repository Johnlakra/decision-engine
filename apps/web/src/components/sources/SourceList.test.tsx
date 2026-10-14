// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SourceList } from "./SourceList";

const ID_A = "0192f0c2-7a1e-7c3b-9d1e-2f4a5b6c7d8e";
const ID_B = "0192f0c2-7a1e-7c3b-9d1e-2f4a5b6c7d8f";

function source(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    type: "rss",
    name,
    slug: name.toLowerCase(),
    enabled: true,
    niche_hint: null,
    last_polled_at: "2026-10-14T05:00:00Z",
    error_count: 0,
    items_today: 4,
    ...extra,
  };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderList(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SourceList locale="en" />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SourceList", () => {
  it("lists sources sorted by name with health text, items today and error count", async () => {
    const data = [source(ID_B, "Zeta", { error_count: 3 }), source(ID_A, "Alpha")];
    vi.stubGlobal("fetch", vi.fn(async () => json({ data })));

    renderList();

    const items = await screen.findAllByRole("listitem");
    const rows = items.filter((item) => item.querySelector('[role="switch"]'));
    expect(rows.map((row) => row.querySelector("h2")?.textContent)).toEqual(["Alpha", "Zeta"]);
    expect(within(rows[0]!).getByText("Healthy")).toBeTruthy();
    expect(within(rows[1]!).getByText("Failing (3 errors)")).toBeTruthy();
    expect(within(rows[0]!).getByText("4 items today")).toBeTruthy();
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ data: [] })));

    renderList();

    expect(await screen.findByText("No sources yet. Add one below.")).toBeTruthy();
  });

  it("shows an error with retry", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({}, 500)));

    renderList();

    expect((await screen.findByRole("alert")).textContent).toBe("Could not load sources.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("patches only enabled and flips the switch at once", async () => {
    let enabled = true;
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        enabled = false;
        return json(source(ID_A, "Alpha", { enabled }));
      }
      return json({ data: [source(ID_A, "Alpha", { enabled })] });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderList();
    const toggle = await screen.findByRole("switch", { name: "Alpha" });

    fireEvent.click(toggle);

    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("false"));
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(call?.[0]).toBe(`/api/v1/sources/${ID_A}`);
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ enabled: false });
  });

  it("rolls the switch back and says so when the patch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init?: RequestInit) =>
        init?.method === "PATCH" ? json({}, 403) : json({ data: [source(ID_A, "Alpha")] }),
      ),
    );
    renderList();
    const toggle = await screen.findByRole("switch", { name: "Alpha" });

    fireEvent.click(toggle);

    expect((await screen.findByRole("alert")).textContent).toBe("Could not change this source. Only admins can.");
    await waitFor(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));
  });
});
