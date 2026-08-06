import type { Metadata } from "next";
import { headers } from "next/headers";
import { AppShell } from "@/components/AppShell";
import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/lib/config/product";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: PRODUCT_NAME,
    template: `%s · ${PRODUCT_NAME}`,
  },
  description: PRODUCT_DESCRIPTION,
};

/**
 * Reading the `x-nonce` header set by `proxy.ts` is what makes Next.js
 * stamp that nonce onto the scripts/styles it injects -- without this read
 * here, Next never applies one and every script Next generates is silently
 * unnonced, which a strict `script-src 'nonce-...' 'strict-dynamic'` CSP
 * then blocks outright (breaks hydration site-wide).
 *
 * This read is also what forces every route in the app to render
 * dynamically rather than via ISR: a nonce must be unique per response, so
 * it can never be correct on a cached/revalidated page (see docs/frontend.md,
 * "Caching behavior").
 */
export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The value itself is never used directly -- reading the `x-nonce`
  // header here is what triggers Next's internal nonce propagation onto
  // the scripts/styles it injects into this render.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const nonce = (await headers()).get("x-nonce");

  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
