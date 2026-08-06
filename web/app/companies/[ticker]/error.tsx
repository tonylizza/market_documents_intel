"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";

/**
 * Route-level boundary (not an in-page catch) so a transient DB failure
 * makes Next.js treat the request as a failed render -- ISR then keeps
 * serving the last good cached page instead of caching this error state.
 * See docs/frontend.md ("Caching behavior").
 */
export default function CompanyPageError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    if (error.digest) {
      console.error("Failed to load company page data, digest:", error.digest);
    }
  }, [error]);

  return <ErrorState title="This company page is temporarily unavailable" />;
}
