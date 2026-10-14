import { cookies } from "next/headers";
import { SourceList } from "@/components/sources/SourceList";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function SourcesPage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <SourceList locale={locale} />;
}
