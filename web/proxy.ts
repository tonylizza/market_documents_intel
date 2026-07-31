import { NextRequest, NextResponse } from "next/server";

// Milestone 7B.1a: renamed from `middleware.ts` to `proxy.ts` (Next.js 16's
// replacement file convention -- the exported function is renamed
// `middleware` -> `proxy`; `config.matcher` and all header logic are
// unchanged). This was the confirmed root cause of a production-only
// regression: routes that
// call `notFound()` (companies/[ticker], comparisons/[id](/evidence),
// passages/[passageComparisonId]) returned HTTP 200 instead of 404 whenever
// `middleware.ts` was present under Next 16.2.12, and returned genuine 404s
// the moment the file was renamed to `proxy.ts` -- verified directly by
// temporarily removing `middleware.ts` and re-running
// `tests/production/http-status.test.ts` (13/13 passed with it absent, 9/13
// with it present under the old filename).
//
// Next.js's own hydration/streaming runtime relies on inline <script> tags
// (RSC boundary-swap scripts, dev-mode HMR bootstrap). A static
// `script-src 'self'` CSP (previously set in next.config.ts) blocks those
// unconditionally -- the page renders server-side but never finishes
// hydrating in a real browser. A per-request nonce is the only CSP
// mechanism that both allows Next's inline scripts and forbids injected
// ones; it must be generated here (middleware), not in next.config.ts,
// because next.config.ts headers are static and can't vary per request.
// Forwarding the nonce via a request header lets the App Router read it
// (via `headers()`) and stamp it onto every inline script it renders.
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const cspHeader = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", cspHeader);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set("Content-Security-Policy", cspHeader);

  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
