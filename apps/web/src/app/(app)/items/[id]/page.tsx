import { cookies } from "next/headers";
import { ItemDetailView } from "@/components/item/ItemDetailView";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

export default async function ItemPage({ params }: { readonly params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return <ItemDetailView itemId={id} locale={locale} />;
}
