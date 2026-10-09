import { describe, expect, it } from "vitest";
import fixture from "./fixture.json";
import { InvalidSignature, verifySignature } from "../src/verifySignature";

const { secret, body, timestamp, header } = fixture;

describe("verifySignature", () => {
  it("accepts a server-signed body", async () => {
    await expect(verifySignature(secret, body, header, { now: timestamp })).resolves.toBeUndefined();
  });

  it("rejects a tampered body", async () => {
    await expect(verifySignature(secret, `${body} `, header, { now: timestamp })).rejects.toThrow(
      InvalidSignature,
    );
  });

  it("rejects a stale timestamp", async () => {
    await expect(verifySignature(secret, body, header, { now: timestamp + 301 })).rejects.toThrow(
      "timestamp outside tolerance",
    );
  });

  it("rejects a malformed header", async () => {
    await expect(verifySignature(secret, body, "nope", { now: timestamp })).rejects.toThrow(
      "malformed",
    );
  });
});
