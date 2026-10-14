import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { NicheEditor } from "@/components/niches/NicheEditor";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";
import { isNicheName } from "@/lib/niches/name";

export default async function NichePage({ params }: { readonly params: Promise<{ name: string }> }) {
  const { name } = await params;
  if (!isNicheName(name)) {
    notFound();
  }
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <NicheEditor name={name} locale={locale} />;
}
