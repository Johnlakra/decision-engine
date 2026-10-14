/** One fetch wrapper for every browser call to the proxy. Never sends an API key. */

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly errors: readonly unknown[];

  constructor(status: number, errors: readonly unknown[] = []) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.errors = errors;
  }
}

async function problemErrors(response: Response): Promise<readonly unknown[]> {
  try {
    const problem: unknown = await response.json();
    const errors = (problem as { errors?: unknown } | null)?.errors;
    return Array.isArray(errors) ? errors : [];
  } catch {
    return [];
  }
}

export async function requestJson<T>(
  method: "GET" | "POST" | "PUT" | "PATCH",
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(response.status, await problemErrors(response));
  }
  return (await response.json()) as T;
}
