import type { PassageSearchPage } from "@/lib/domain/passage";
import { MAX_COUNTED_PASSAGE_RESULTS } from "@/lib/domain/passage";
import { PassageResultCard } from "@/components/PassageResultCard";
import { PaginationNav } from "@/components/PaginationNav";
import { EmptyState } from "@/components/EmptyState";
import { buildPassageSearchQueryString } from "@/lib/services/passage-search-params";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./PassageResultsList.module.css";

export interface PassageResultsListProps {
  page: PassageSearchPage;
}

/** Result list + accessible result-count announcement + pagination -- the
 * count text is the single source of truth a screen reader announces on
 * every search/filter change (`role="status"`/`aria-live="polite"`). */
export function PassageResultsList({ page }: PassageResultsListProps) {
  if (page.results.length === 0) {
    return (
      <EmptyState
        title="No results for these filters"
        description="Try a different search term, a broader phrase, or fewer filters."
      />
    );
  }

  const countLabel = page.pagination.totalIsCapped
    ? `Showing the first ${formatCount(MAX_COUNTED_PASSAGE_RESULTS)}+ results -- narrow your search for a precise count`
    : `${formatCount(page.pagination.totalCount)} result${page.pagination.totalCount === 1 ? "" : "s"}`;

  return (
    <div>
      <p role="status" aria-live="polite" className={styles.count}>
        {countLabel}
      </p>
      <div className={styles.list}>
        {page.results.map((result) => (
          <PassageResultCard key={`${result.passageId}-${result.passageComparisonId ?? "none"}`} result={result} />
        ))}
      </div>
      <PaginationNav
        pagination={page.pagination}
        buildHref={(targetPage) => `/passages?${buildPassageSearchQueryString({ ...page.params, page: targetPage })}`}
        label="Passage search results pagination"
      />
    </div>
  );
}
