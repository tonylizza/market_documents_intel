import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div style={{ paddingBlock: "var(--space-8)" }}>
      <EmptyState title="Page not found" description="The page you're looking for doesn't exist or may have moved." />
      <p style={{ marginTop: "var(--space-4)" }}>
        <Link href="/">Return to the Companies home page</Link>
      </p>
    </div>
  );
}
