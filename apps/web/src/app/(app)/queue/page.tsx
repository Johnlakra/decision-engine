import { cookies } from "next/headers";
import { QueueView } from "@/components/queue/QueueView";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function QueuePage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <QueueView locale={locale} />;
}
