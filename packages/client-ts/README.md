# @decision-engine/client

Typed TypeScript client for the Decision Engine `/v1` API. Types come from `openapi-typescript`
(`src/schema.d.ts`, generated, do not edit); requests go through `openapi-fetch`. Node >= 22, Next.js
route handlers, Expo (server-side or via your own backend). Keep the API key on the server.

```ts
import { createClient } from "@decision-engine/client";

const de = createClient({ baseUrl: "https://de.example.com", apiKey: process.env.DE_API_KEY ?? "" });

const { data, error } = await de.POST("/v1/items", {
  body: { source: "radar", source_ref: "story-42", payload: { title: "Hello" } },
});
if (error) throw new Error("ingest failed");
console.log(data.id);

const page = await de.GET("/v1/items", { params: { query: { status: "pending", limit: 20 } } });
```

## Verify a webhook

```ts
import { verifySignature } from "@decision-engine/client";

// Next.js route handler: read the RAW body, never re-serialize parsed JSON.
export async function POST(req: Request) {
  const raw = await req.text();
  await verifySignature(process.env.DE_WEBHOOK_SECRET ?? "", raw, req.headers.get("X-DE-Signature") ?? "");
  return new Response("ok");
}
```

It throws `InvalidSignature` for a malformed header, a timestamp outside 300 s (`toleranceS`), or a mismatch.

## Develop

`npm ci`, `npm run gen` (regenerate types from `../openapi.json`), `npm run lint`, `npm test`, `npm run build`.
Regenerate everything from the repo root with `make sdk`.
