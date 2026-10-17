// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsForm } from "./SettingsForm";

const SETTINGS = {
  quiet_hours: [22, 7],
  digest_hour: 8,
  ping_cap_per_day: 5,
  interests: ["ai", "grants"],
  languages: ["en", "hi"],
};

let fetchMock: ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

function putCalls(): [string, RequestInit][] {
  return fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
  ) as [string, RequestInit][];
}

async function renderForm(): Promise<void> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SettingsForm locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: "Settings" });
}

beforeEach(() => {
  fetchMock = vi.fn(async () => jsonResponse(SETTINGS));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SettingsForm", () => {
  it("loads the saved values into the form", async () => {
    await renderForm();

    expect((screen.getByLabelText("Daily digest at") as HTMLSelectElement).value).toBe("8");
    expect((screen.getByLabelText("From") as HTMLSelectElement).value).toBe("22");
    expect((screen.getByLabelText("To") as HTMLSelectElement).value).toBe("7");
    expect((screen.getByLabelText(/Urgent pings per day/) as HTMLInputElement).value).toBe("5");
    expect((screen.getByLabelText(/Interests/) as HTMLInputElement).value).toBe("ai, grants");
    expect((screen.getByLabelText("English") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("हिन्दी") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("ਪੰਜਾਬੀ") as HTMLInputElement).checked).toBe(false);
  });

  it("shows a field error and does not send when the ping cap is out of range", async () => {
    await renderForm();

    fireEvent.change(screen.getByLabelText(/Urgent pings per day/), { target: { value: "99" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Pings per day must be a whole number up to 50.");
    expect(putCalls()).toHaveLength(0);
  });

  it("requires at least one language", async () => {
    await renderForm();

    fireEvent.click(screen.getByLabelText("English"));
    fireEvent.click(screen.getByLabelText("हिन्दी"));
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Choose at least one language.");
    expect(putCalls()).toHaveLength(0);
  });

  it("sends a PUT with the exact payload and confirms the save", async () => {
    await renderForm();

    fireEvent.change(screen.getByLabelText("Daily digest at"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText(/Urgent pings per day/), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText(/Interests/), { target: { value: " ai , , funding " } });
    fireEvent.click(screen.getByLabelText("ਪੰਜਾਬੀ"));
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await screen.findByRole("status");
    const [call] = putCalls();
    const [url, init] = call ?? ["", {}];
    expect(url).toBe("/api/v1/settings");
    expect(JSON.parse(init.body as string)).toEqual({
      quiet_hours: [22, 7],
      digest_hour: 9,
      ping_cap_per_day: 3,
      interests: ["ai", "funding"],
      languages: ["en", "hi", "pa"],
      laya_mode: null,
    });
  });

  it("offers the server default plus off and shadow, and saves the chosen mode", async () => {
    await renderForm();
    const select = screen.getByLabelText("Laya triage mode") as HTMLSelectElement;

    expect(select.value).toBe("env");
    expect([...select.options].map((option) => option.value)).toEqual(["env", "off", "shadow"]);
    fireEvent.change(select, { target: { value: "shadow" } });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await screen.findByRole("status");
    const [call] = putCalls();
    expect(JSON.parse((call?.[1].body as string) ?? "{}")).toMatchObject({ laya_mode: "shadow" });
  });

  it("shows a generic error when the save is rejected", async () => {
    await renderForm();
    fetchMock.mockImplementation(async (_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? new Response("{}", { status: 422 }) : jsonResponse(SETTINGS),
    );

    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Could not load or save"));
  });
});
