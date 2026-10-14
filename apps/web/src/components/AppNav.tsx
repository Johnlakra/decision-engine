"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { translate, type Locale } from "@/lib/i18n";

const SECTIONS = [
  { href: "/queue", key: "nav.queue" },
  { href: "/history", key: "nav.history" },
  { href: "/sources", key: "nav.sources" },
  { href: "/insights", key: "nav.insights" },
  { href: "/settings", key: "nav.settings" },
] as const;

interface AppNavProps {
  readonly locale: Locale;
}

/** Section links for signed-in screens. The locale comes from the server, so no flicker. */
export function AppNav({ locale }: AppNavProps) {
  const pathname = usePathname();

  return (
    <nav aria-label={translate(locale, "app.name")} className="border-b border-border bg-surface">
      <ul className="mx-auto flex max-w-[760px] gap-4 px-4 py-2 text-[14px]">
        {SECTIONS.map((section) => {
          const active = pathname === section.href || pathname.startsWith(`${section.href}/`);
          return (
            <li key={section.href}>
              <Link
                href={section.href}
                aria-current={active ? "page" : undefined}
                className={active ? "font-semibold text-text underline underline-offset-4" : "text-muted"}
              >
                {translate(locale, section.key)}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
