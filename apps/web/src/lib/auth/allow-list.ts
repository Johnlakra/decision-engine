/**
 * Google accounts allowed to sign in (CLAUDE.md rule 1: private to the owners).
 * Fails closed: an empty or missing list admits nobody.
 */

const SEPARATOR = ",";

export function parseAllowList(raw: string | undefined): ReadonlySet<string> {
  const entries = (raw ?? "")
    .split(SEPARATOR)
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry) => entry.length > 0);
  return new Set(entries);
}

export function isAllowedEmail(email: string | null | undefined, allowed: ReadonlySet<string>): boolean {
  if (!email) {
    return false;
  }
  return allowed.has(email.trim().toLowerCase());
}
