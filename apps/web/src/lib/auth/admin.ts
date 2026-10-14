import { isAllowedEmail } from "@/lib/auth/allow-list";

/**
 * The proxy uses one server API key with admin scope, so settings writes are gated here:
 * only emails in ADMIN_EMAILS (parsed with parseAllowList) may PUT /settings or /niches. Empty = nobody.
 */

const ADMIN_WRITE_RESOURCES: readonly string[] = ["settings", "niches"];

export const isAdminEmail = isAllowedEmail;

export function canProxy(
  method: string,
  segments: readonly string[],
  email: string | null | undefined,
  admins: ReadonlySet<string>,
): boolean {
  const isAdminWrite = method === "PUT" && ADMIN_WRITE_RESOURCES.includes(segments[0] ?? "");
  return !isAdminWrite || isAdminEmail(email, admins);
}
