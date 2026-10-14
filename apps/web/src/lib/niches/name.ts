/** Niche names are lowercase slugs (schemas/niche.schema.json). */
export const NICHE_NAME_PATTERN = /^[a-z][a-z0-9_]{1,39}$/;

export function isNicheName(value: string): boolean {
  return NICHE_NAME_PATTERN.test(value);
}
