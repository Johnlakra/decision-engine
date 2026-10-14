import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, requestJson } from "./request";
import { decisionErrorKey } from "@/lib/item/decision-error";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/problem+json" } })),
  );
}

describe("requestJson errors", () => {
  it("keeps the status and the problem body's errors", async () => {
    stubFetch(422, { title: "bad", errors: [{ json_pointer: "/note", message: "too long" }] });

    const error = await requestJson("POST", "/x", {}).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(422);
    expect((error as ApiError).errors).toEqual([{ json_pointer: "/note", message: "too long" }]);
  });

  it("tolerates a non-JSON error body", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("oops", { status: 500 })));

    const error = (await requestJson("GET", "/x").catch((e: unknown) => e)) as ApiError;

    expect(error.status).toBe(500);
    expect(error.errors).toEqual([]);
  });
});

describe("decisionErrorKey", () => {
  it("maps 409 to the already-handled message and everything else to the generic one", () => {
    expect(decisionErrorKey(new ApiError(409))).toBe("item.errors.alreadyHandled");
    expect(decisionErrorKey(new ApiError(422))).toBe("queue.failed");
    expect(decisionErrorKey(new Error("network"))).toBe("queue.failed");
  });
});
