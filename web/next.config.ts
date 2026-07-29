import type { NextConfig } from "next";

// Content-Security-Policy is set per-request in middleware.ts instead of
// here -- it needs a fresh nonce on every request (for Next.js's own
// inline hydration/streaming scripts), and next.config.ts headers are
// static, so they can't carry a nonce.
const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
