"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";

/** Route-level boundary for DB failures propagated from page.tsx. */
export default function DiscoverError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    if (error.digest) {
      console.error("Failed to load discovery page data, digest:", error.digest);
    }
  }, [error]);

  return <ErrorState title="Discovery rankings are temporarily unavailable" />;
}
