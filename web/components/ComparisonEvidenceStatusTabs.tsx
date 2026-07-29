import Link from "next/link";
import type { AlignmentStatus, ComparisonEvidenceFilters, ComparisonEvidenceSummary } from "@/lib/domain/passage";
import { ALIGNMENT_STATUSES, formatAlignmentStatusLabel } from "@/lib/config/passage-vocabulary";
import { buildComparisonEvidenceQueryString, resetEvidencePage } from "@/lib/services/comparison-evidence-params";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./ComparisonEvidenceStatusTabs.module.css";

export interface ComparisonEvidenceStatusTabsProps {
  comparisonId: string;
  filters: ComparisonEvidenceFilters;
  summary: ComparisonEvidenceSummary;
}

/**
 * A real, server-rendered link-based segmented control (not an ARIA
 * `tab`/`tabpanel` pair) -- each "tab" is a full navigation to a new,
 * shareable URL with `status=` set and `page` reset to `1`, so ordinary
 * `Tab`/`Enter` keyboard navigation and screen readers both work without
 * any client-side roving-tabindex logic. The current status is exposed via
 * `aria-current="page"`.
 */
export function ComparisonEvidenceStatusTabs({ comparisonId, filters, summary }: ComparisonEvidenceStatusTabsProps) {
  const baseHref = `/comparisons/${comparisonId}/evidence`;

  function hrefFor(status: AlignmentStatus | "ALL"): string {
    const nextFilters = resetEvidencePage({ ...filters, status });
    const query = buildComparisonEvidenceQueryString(nextFilters);
    return query ? `${baseHref}?${query}` : baseHref;
  }

  const tabs: { status: AlignmentStatus | "ALL"; label: string; count: number }[] = [
    { status: "ALL", label: "All", count: summary.totalCount },
    ...ALIGNMENT_STATUSES.map((status) => ({ status, label: formatAlignmentStatusLabel(status), count: summary.counts[status] })),
  ];

  return (
    <nav aria-label="Evidence status" className={styles.tabs}>
      {tabs.map((tab) => (
        <Link
          key={tab.status}
          href={hrefFor(tab.status)}
          aria-current={filters.status === tab.status ? "page" : undefined}
          className={`${styles.tab} ${filters.status === tab.status ? styles.active : ""}`}
        >
          {tab.label}
          <span className={styles.count}>{formatCount(tab.count)}</span>
        </Link>
      ))}
    </nav>
  );
}
