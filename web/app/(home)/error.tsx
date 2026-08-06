"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";

/** Route-level boundary for DB failures propagated from page.tsx. */
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
