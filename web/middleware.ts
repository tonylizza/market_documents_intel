import { NextRequest, NextResponse } from "next/server";

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
export function middleware(request: NextRequest) {
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
