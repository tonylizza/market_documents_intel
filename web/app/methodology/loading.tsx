import { LoadingSkeleton } from "@/components/LoadingSkeleton";

export default function Loading() {
  return (
    <div style={{ paddingBlock: "var(--space-6)" }}>
      <LoadingSkeleton count={3} label="Loading page content" />
    </div>
  );
}
