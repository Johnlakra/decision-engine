import { cookies } from "next/headers";
import { NicheList } from "@/components/niches/NicheList";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function NichesPage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <NicheList locale={locale} />;
}
