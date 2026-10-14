import { isAllowedEmail } from "@/lib/auth/allow-list";

/**
 * The proxy uses one server API key with admin scope, so settings writes are gated here:
 * only emails in ADMIN_EMAILS (parsed with parseAllowList) may PUT /settings. Empty = nobody.
 */

export const isAdminEmail = isAllowedEmail;

export function canProxy(
  method: string,
  segments: readonly string[],
  email: string | null | undefined,
  admins: ReadonlySet<string>,
): boolean {
  const isSettingsWrite = method === "PUT" && segments[0] === "settings";
  return !isSettingsWrite || isAdminEmail(email, admins);
}
