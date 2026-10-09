/** Verify `X-DE-Signature: t=<unix>,v1=<hex>` (HMAC-SHA-256 over `"<t>." + body`). Web Crypto only. */

export class InvalidSignature extends Error {
  constructor(public readonly reason: string) {
    super(reason);
    this.name = "InvalidSignature";
  }
}

export interface VerifyOptions {
  /** Max clock skew in seconds. Default 300. */
  toleranceS?: number;
  /** Override "now" (unix seconds), for tests. */
  now?: number;
}

const HEADER = /^t=(\d+),v1=([0-9a-f]{64})$/;
const encoder = new TextEncoder();

function toHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Resolves when valid; rejects with InvalidSignature otherwise. `body` must be the raw bytes/text. */
export async function verifySignature(
  secret: string | Uint8Array,
  body: string | Uint8Array,
  header: string,
  { toleranceS = 300, now = Math.floor(Date.now() / 1000) }: VerifyOptions = {},
): Promise<void> {
  const match = HEADER.exec(header);
  if (match === null) throw new InvalidSignature("malformed signature header");
  const stamp = Number(match[1]);
  if (Math.abs(now - stamp) > toleranceS) throw new InvalidSignature("timestamp outside tolerance");

  const keyBytes = typeof secret === "string" ? encoder.encode(secret) : new Uint8Array(secret);
  const bodyBytes = typeof body === "string" ? encoder.encode(body) : new Uint8Array(body);
  const prefix = encoder.encode(`${stamp}.`);
  const message = new Uint8Array(prefix.length + bodyBytes.length);
  message.set(prefix, 0);
  message.set(bodyBytes, prefix.length);

  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const expected = toHex(await crypto.subtle.sign("HMAC", key, message));
  if (!constantTimeEqual(expected, match[2] ?? "")) throw new InvalidSignature("signature mismatch");
}
