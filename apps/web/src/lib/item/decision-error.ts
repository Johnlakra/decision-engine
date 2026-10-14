import { ApiError } from "@/lib/api/request";

const CONFLICT = 409;

/** Message key for a failed decision call. 409 = handled elsewhere; the rest is generic. */
export function decisionErrorKey(error: unknown): string {
  return error instanceof ApiError && error.status === CONFLICT
    ? "item.errors.alreadyHandled"
    : "queue.failed";
}
