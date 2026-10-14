// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AddSourceForm } from "./AddSourceForm";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderForm(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AddSourceForm locale="en" />
    </QueryClientProvider>,
  );
}

function fill(label: string, value: string): void {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AddSourceForm", () => {
  it("offers only rss and google news", () => {
    renderForm();

    const options = Array.from(screen.getByLabelText("Type").querySelectorAll("option")).map((o) => o.value);
    expect(options).toEqual(["rss", "google_news"]);
  });

  it("blocks an invalid draft without calling the API", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderForm();

    fireEvent.click(screen.getByRole("button", { name: "Add source" }));

    expect(screen.getByText("Enter a name.")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the draft and clears the form", async () => {
    const fetchMock = vi.fn(async () => json({ id: "x" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    renderForm();
    fill("Name", "Example feed");
    fill("Slug", "example-feed");
    fill("Feed URL", "https://example.com/feed.xml");

    fireEvent.click(screen.getByRole("button", { name: "Add source" }));

    await waitFor(() => expect(screen.getByText("Source added.")).toBeTruthy());
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      type: "rss",
      name: "Example feed",
      slug: "example-feed",
      config: { url: "https://example.com/feed.xml" },
    });
  });

  it("shows 409 as a taken slug next to the slug field", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({}, 409)));
    renderForm();
    fill("Name", "Example");
    fill("Slug", "example");
    fill("Feed URL", "https://example.com/feed.xml");

    fireEvent.click(screen.getByRole("button", { name: "Add source" }));

    expect((await screen.findByText("That slug is taken.")).id).toBe(screen.getByLabelText("Slug").getAttribute("aria-describedby"));
  });

  it("shows 422 pointer errors next to their fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => json({ errors: [{ field: "body.config", message: "private address", code: "value_error" }] }, 422)),
    );
    renderForm();
    fill("Name", "Example");
    fill("Slug", "example");
    fill("Feed URL", "https://example.com/feed.xml");

    fireEvent.click(screen.getByRole("button", { name: "Add source" }));

    expect(await screen.findByText("private address")).toBeTruthy();
    expect(screen.getByLabelText("Feed URL").getAttribute("aria-invalid")).toBe("true");
  });

  it("switches the value field to a query for google news", () => {
    renderForm();

    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "google_news" } });

    expect(screen.getByLabelText("Search query")).toBeTruthy();
  });
});
