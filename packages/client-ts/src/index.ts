import createFetchClient from "openapi-fetch";
import type { paths } from "./schema";

export type { components, paths } from "./schema";
export { InvalidSignature, verifySignature } from "./verifySignature";
export type { VerifyOptions } from "./verifySignature";

export interface ClientOptions {
  baseUrl: string;
  /** Server-side only. Never ship an API key to a browser. */
  apiKey: string;
  fetch?: typeof fetch;
}

/** Typed client over `/v1`. Add retries in your own fetch if you need them. */
export function createClient({ baseUrl, apiKey, fetch: fetchImpl }: ClientOptions) {
  return createFetchClient<paths>({
    baseUrl,
    headers: { Authorization: `Bearer ${apiKey}` },
    ...(fetchImpl ? { fetch: fetchImpl } : {}),
  });
}
