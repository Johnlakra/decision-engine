import en from "@/messages/en.json";
import hi from "@/messages/hi.json";
import pa from "@/messages/pa.json";

/** Locales the UI ships (docs/UI_UX.md section 6: en, hi, pa). English is the fallback. */
export const LOCALES = ["en", "hi", "pa"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "de_locale";

type Catalog = Readonly<Record<string, string>>;
const CATALOGS: Readonly<Record<Locale, Catalog>> = { en, hi, pa };

export function resolveLocale(value: string | null | undefined): Locale {
  return LOCALES.find((locale) => locale === value) ?? DEFAULT_LOCALE;
}

/**
 * Look up a message, substitute `{name}` placeholders, fall back to English, then to the key.
 * Placeholder values are plain text; React escapes them when rendered.
 */
export function translate(
  locale: Locale,
  key: string,
  values: Readonly<Record<string, string | number>> = {},
): string {
  const template = CATALOGS[locale][key] ?? CATALOGS[DEFAULT_LOCALE][key] ?? key;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match,
  );
}
