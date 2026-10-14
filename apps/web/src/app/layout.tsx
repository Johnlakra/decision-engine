import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";
import "./globals.css";

export const metadata: Metadata = {
  title: "Decision Engine",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { readonly children: ReactNode }) {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <html lang={locale}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
