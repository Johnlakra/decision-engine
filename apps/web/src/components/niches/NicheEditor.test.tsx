// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NicheEditor } from "./NicheEditor";

const CONFIG = {
  name: "inbox",
  label: "Inbox",
  description: "a personal email or message",
  enabled: true,
  autonomy: "ask",
  actions: ["archive"],
  auto_actions: [],
  prompt: "x".repeat(50),
};
const DETAIL = {
  name: "inbox",
  source: "yaml",
  version: 1,
  config: CONFIG,
  yaml: "name: inbox\nautonomy: ask\n",
};

let putStatus = 200;
let putBody: unknown = { ...DETAIL, version: 2 };
let fetchMock: ReturnType<typeof vi.fn>;

function putCalls(): [string, RequestInit][] {
  return fetchMock.mock.calls.filter(
    ([, init]) => (init as RequestInit | undefined)?.method === "PUT",
  ) as [string, RequestInit][];
}

async function renderEditor(): Promise<void> {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <NicheEditor name="inbox" locale="en" />
    </QueryClientProvider>,
  );
  await screen.findByLabelText("Label");
}

function openYamlTab(): void {
  fireEvent.click(screen.getByRole("tab", { name: "Advanced: YAML" }));
}

beforeEach(() => {
  putStatus = 200;
  putBody = { ...DETAIL, version: 2 };
  fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === "PUT"
      ? new Response(JSON.stringify(putBody), { status: putStatus })
      : new Response(JSON.stringify(DETAIL), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NicheEditor", () => {
  it("loads the config into the basic form", async () => {
    await renderEditor();

    expect((screen.getByLabelText("Label") as HTMLInputElement).value).toBe("Inbox");
    expect((screen.getByLabelText("Autonomy") as HTMLSelectElement).value).toBe("ask");
    expect((screen.getByLabelText("Actions (one per line)") as HTMLTextAreaElement).value).toBe("archive");
  });

  it("saves the whole config as JSON, keeping keys the form does not show", async () => {
    await renderEditor();

    fireEvent.change(screen.getByLabelText("Label"), { target: { value: "Inbox 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    await screen.findByText("Niche saved. Now at version 2.");
    const [url, init] = putCalls()[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/niches/inbox");
    expect(JSON.parse(String(init.body))).toEqual({ ...CONFIG, label: "Inbox 2" });
  });

  it("shows a 422 message next to the field its pointer names", async () => {
    putStatus = 422;
    putBody = {
      errors: [
        { json_pointer: "/autonomy", message: "'yolo' is not one of ['suggest', 'ask', 'auto']" },
        { json_pointer: "/prompt", message: "too short" },
      ],
    };
    await renderEditor();

    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    const message = await screen.findByText("'yolo' is not one of ['suggest', 'ask', 'auto']");
    expect(message.closest("div")?.textContent).toContain("Autonomy");
    expect(screen.getByLabelText("Autonomy").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("too short")).toBeTruthy();
    expect(screen.getByText("/prompt")).toBeTruthy();
  });

  it("tells a non-admin that only admins can change niches", async () => {
    putStatus = 403;
    putBody = { error: "Admin only" };
    await renderEditor();

    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Only admins can change niches.");
  });

  it("shows YAML syntax errors on the client and blocks the save", async () => {
    await renderEditor();
    openYamlTab();

    fireEvent.change(screen.getByLabelText("Niche YAML"), { target: { value: "name: a\nactions: [one\n" } });

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/^Line \d+, column \d+:/));
    expect((screen.getByRole("button", { name: "Save niche" }) as HTMLButtonElement).disabled).toBe(true);
    expect(putCalls()).toHaveLength(0);
  });

  it("sends the YAML edit when saved right after typing", async () => {
    await renderEditor();
    openYamlTab();

    fireEvent.change(screen.getByLabelText("Niche YAML"), { target: { value: "name: inbox\nautonomy: suggest\n" } });
    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    await screen.findByText("Niche saved. Now at version 2.");
    const [, init] = putCalls()[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ name: "inbox", autonomy: "suggest" });
  });

  it("lists every server error above the YAML editor", async () => {
    putStatus = 422;
    putBody = { errors: [{ json_pointer: "/actions/0", message: "unknown action" }] };
    await renderEditor();
    openYamlTab();

    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    expect(await screen.findByText("/actions/0")).toBeTruthy();
    expect(screen.getByText(/unknown action/)).toBeTruthy();
  });

  it("asks for confirmation, listing auto actions, before saving autonomy auto", async () => {
    await renderEditor();
    fireEvent.change(screen.getByLabelText("Automatic actions (one per line)"), { target: { value: "archive" } });
    fireEvent.change(screen.getByLabelText("Autonomy"), { target: { value: "auto" } });

    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("archive");
    expect(putCalls()).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Save with auto" }));
    await screen.findByText("Niche saved. Now at version 2.");
    expect(putCalls()).toHaveLength(1);
  });

  it("does not save when the auto confirmation is cancelled", async () => {
    await renderEditor();
    fireEvent.change(screen.getByLabelText("Autonomy"), { target: { value: "auto" } });

    fireEvent.click(screen.getByRole("button", { name: "Save niche" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(putCalls()).toHaveLength(0);
  });
});
