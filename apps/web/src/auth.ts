import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { isAllowedEmail, parseAllowList } from "@/lib/auth/allow-list";

/**
 * Google sign-in, admitted only for ALLOWED_EMAILS (fails closed when unset).
 * Auth.js reads AUTH_SECRET, AUTH_GOOGLE_ID and AUTH_GOOGLE_SECRET from the environment.
 */
const allowed = parseAllowList(process.env.ALLOWED_EMAILS);

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  pages: { signIn: "/login" },
  callbacks: {
    signIn({ profile }) {
      return isAllowedEmail(profile?.email, allowed);
    },
  },
});
