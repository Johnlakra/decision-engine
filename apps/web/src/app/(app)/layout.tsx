import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { auth } from "@/auth";
import { AppNav } from "@/components/AppNav";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";

/** Every signed-in screen shares this layout. The sign-in check here covers the whole group. */
export default async function AppLayout({ children }: { readonly children: ReactNode }) {
  const session = await auth();
  if (!session) {
    redirect("/login");
  }
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <div className="min-h-screen">
      <AppNav locale={locale} />
      <main>{children}</main>
    </div>
  );
}
