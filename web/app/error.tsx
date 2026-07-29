"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/ErrorState";

export default function GlobalError({ error }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Server-side rendering already logs the original error with redacted
    // context (see each page's try/catch); this logs only the digest for
    // client-side correlation, never the error message itself, which may
    // originate from a dependency and isn't guaranteed to be redacted.
    if (error.digest) {
      console.error("Unhandled application error, digest:", error.digest);
    }
  }, [error]);

  return (
    <div className="container" style={{ paddingBlock: "var(--space-8)" }}>
      <ErrorState
        title="Something went wrong"
        description="An unexpected error occurred while rendering this page. Please try again."
      />
    </div>
  );
}
