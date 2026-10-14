import { cookies } from "next/headers";
import { SettingsForm } from "@/components/settings/SettingsForm";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function SettingsPage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <SettingsForm locale={locale} />;
}
