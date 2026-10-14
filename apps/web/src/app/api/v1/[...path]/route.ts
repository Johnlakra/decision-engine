import { NextResponse, type NextRequest } from "next/server";
import { auth } from "@/auth";
import { planProxy } from "@/lib/proxy/route-policy";

/** Server-side proxy to the Decision Engine API. The API key never leaves the server. */

const MAX_BODY_BYTES = 16 * 1024; // decisions are small; anything larger is refused

type RouteContext = { params: Promise<{ path: string[] }> };

function errorResponse(status: number, detail: string): NextResponse {
  return NextResponse.json({ error: detail }, { status });
}

async function readBoundedBody(request: NextRequest): Promise<string | null> {
  const declared = Number(request.headers.get("content-length") ?? 0);
  if (declared > MAX_BODY_BYTES) {
    return null;
  }
  const text = await request.text();
  return new TextEncoder().encode(text).byteLength > MAX_BODY_BYTES ? null : text;
}

async function forward(request: NextRequest, context: RouteContext): Promise<Response> {
  const session = await auth();
  if (!session) {
    return errorResponse(401, "Sign in required");
  }
  const { path } = await context.params;
  const plan = planProxy(request.method, path, request.nextUrl.searchParams);
  if (!plan.ok) {
    return errorResponse(plan.status, plan.status === 405 ? "Method not allowed" : "Not found");
  }
  const base = process.env.DE_API_URL;
  const apiKey = process.env.DE_API_KEY;
  if (!base || !apiKey) {
    return errorResponse(503, "API is not configured");
  }
  const body = plan.method === "POST" ? await readBoundedBody(request) : undefined;
  if (body === null) {
    return errorResponse(413, "Request body too large");
  }
  try {
    const upstream = await fetch(new URL(`${plan.path}${plan.search}`, base), {
      method: plan.method,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
      redirect: "error",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    // Log the error type only: messages can echo request details.
    console.error("api proxy upstream failed", error instanceof Error ? error.name : "unknown");
    return errorResponse(502, "API is unreachable");
  }
}

export { forward as GET, forward as POST };
