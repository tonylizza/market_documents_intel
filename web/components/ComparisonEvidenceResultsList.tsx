import type { ComparisonEvidenceFilters, ComparisonEvidencePage } from "@/lib/domain/passage";
import { ComparisonEvidenceRow } from "@/components/ComparisonEvidenceRow";
import { PaginationNav } from "@/components/PaginationNav";
import { EmptyState } from "@/components/EmptyState";
import { buildComparisonEvidenceQueryString } from "@/lib/services/comparison-evidence-params";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./ComparisonEvidenceResultsList.module.css";

export interface ComparisonEvidenceResultsListProps {
  comparisonId: string;
  page: ComparisonEvidencePage;
  filters: ComparisonEvidenceFilters;
}

export function ComparisonEvidenceResultsList({ comparisonId, page, filters }: ComparisonEvidenceResultsListProps) {
  if (page.items.length === 0) {
    return <EmptyState title="No evidence for these filters" description="Try a different status tab or fewer filters." />;
  }

  return (
    <div>
      <p role="status" aria-live="polite" className={styles.count}>
        {formatCount(page.pagination.totalCount)} evidence item{page.pagination.totalCount === 1 ? "" : "s"}
      </p>
      <div className={styles.list}>
        {page.items.map((item) => (
          <ComparisonEvidenceRow key={item.passageComparisonId} item={item} />
        ))}
      </div>
      <PaginationNav
        pagination={page.pagination}
        buildHref={(targetPage) =>
          `/comparisons/${comparisonId}/evidence?${buildComparisonEvidenceQueryString({ ...filters, page: targetPage })}`
        }
        label="Evidence pagination"
      />
    </div>
  );
}
