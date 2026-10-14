import { cookies } from "next/headers";
import { signIn } from "@/auth";
import { LOCALE_COOKIE, resolveLocale, translate } from "@/lib/i18n";

export default async function LoginPage() {
  const cookieStore = await cookies();
  const locale = resolveLocale(cookieStore.get(LOCALE_COOKIE)?.value);
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <h1 className="mb-6 text-[20px] font-semibold">{translate(locale, "app.name")}</h1>
      <form
        action={async () => {
          "use server";
          await signIn("google", { redirectTo: "/queue" });
        }}
      >
        <button
          type="submit"
          className="w-full rounded-[8px] bg-primary px-4 py-3 font-medium text-primary-text"
        >
          {translate(locale, "auth.signIn")}
        </button>
      </form>
    </main>
  );
}
