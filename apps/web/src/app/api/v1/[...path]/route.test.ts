import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const authMock = vi.fn();
vi.mock("@/auth", () => ({ auth: () => authMock() }));

import { NextRequest } from "next/server";
import { GET, PUT } from "./route";

const fetchMock = vi.fn();
const KEY = "de_secret_key";

function call(handler: typeof GET, method: string, path: string[], body?: unknown) {
  const url = `http://localhost/api/v1/${path.join("/")}`;
  const request = new NextRequest(url, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handler(request, { params: Promise.resolve({ path }) });
}

beforeEach(() => {
  process.env.DE_API_URL = "http://engine.test";
  process.env.DE_API_KEY = KEY;
  process.env.ADMIN_EMAILS = "boss@example.com";
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  authMock.mockResolvedValue({ user: { email: "boss@example.com" } });
});

afterEach(() => vi.unstubAllGlobals());

describe("API proxy route", () => {
  it("answers 401 without calling upstream when signed out", async () => {
    authMock.mockResolvedValue(null);

    const response = await call(GET, "GET", ["items"]);

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards a PUT JSON body for an admin", async () => {
    const response = await call(PUT, "PUT", ["settings"], { languages: ["en"] });

    expect(response.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(String(url)).toBe("http://engine.test/v1/settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ languages: ["en"] });
  });

  it("refuses a settings write from a non-admin with 403 and no upstream call", async () => {
    authMock.mockResolvedValue({ user: { email: "user@example.com" } });

    const response = await call(PUT, "PUT", ["settings"], { languages: ["en"] });

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refuses every settings write when ADMIN_EMAILS is empty", async () => {
    process.env.ADMIN_EMAILS = "";

    const response = await call(PUT, "PUT", ["settings"], {});

    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the key upstream and never leaks it to the browser", async () => {
    const response = await call(GET, "GET", ["items"]);

    const [, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBe(`Bearer ${KEY}`);
    const headers = JSON.stringify([...response.headers.entries()]);
    expect(headers).not.toContain(KEY);
    expect(headers.toLowerCase()).not.toContain("authorization");
    expect(await response.text()).not.toContain(KEY);
  });

  it("answers 404 for a disallowed path without calling upstream", async () => {
    const response = await call(GET, "GET", ["admin", "keys"]);

    expect(response.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
