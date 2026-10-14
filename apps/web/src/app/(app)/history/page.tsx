import { cookies } from "next/headers";
import { HistoryView } from "@/components/history/HistoryView";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function HistoryPage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <HistoryView locale={locale} />;
}
