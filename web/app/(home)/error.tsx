"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";

/**
 * Route-level boundary (not an in-page catch) so a transient DB failure
 * makes Next.js treat the request as a failed render -- ISR then keeps
 * serving the last good cached page instead of caching this error state.
 * See docs/frontend.md ("Caching behavior").
 */
export default function CompaniesHomeError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    if (error.digest) {
      console.error("Failed to load Companies home page data, digest:", error.digest);
    }
  }, [error]);

  return (
    <ErrorState
      title="Company data is temporarily unavailable"
      description="We couldn't reach the application database. Please check back shortly."
    />
  );
}
