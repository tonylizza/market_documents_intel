import type { RetrievalPage } from "@/lib/domain/retrieval";
import { RetrievalResultCard } from "@/components/RetrievalResultCard";
import { EmptyState } from "@/components/EmptyState";
import styles from "./RetrievalResultsList.module.css";

export interface RetrievalResultsListProps {
  page: RetrievalPage;
}

/**
 * Semantic/hybrid result list. Unlike `PassageResultsList`, there is no
 * page-count pagination -- semantic/hybrid retrieval always returns a
 * small, bounded result count (see milestone: "maximum final results"),
 * never an unbounded corpus-wide listing.
 */
export function RetrievalResultsList({ page }: RetrievalResultsListProps) {
  if (page.providerUnavailable && page.results.length === 0) {
    return (
      <EmptyState
        title="Semantic search is temporarily unavailable"
        description="The query-embedding service could not be reached. Try Keyword search, or try again shortly."
      />
    );
  }

  if (page.results.length === 0) {
    return (
      <EmptyState
        title="No results for these filters"
        description="Try a different search term, a broader phrase, or fewer filters."
      />
    );
  }

  return (
    <div>
      {page.providerUnavailable && (
        <p role="status" className={styles.notice}>
          The semantic-matching service is temporarily unavailable -- showing keyword-matched results only.
        </p>
      )}
      {page.weakMatchNotice && (
        <p role="status" className={styles.notice}>
          No strong semantic matches were found. Showing the closest available passages.
        </p>
      )}
      <p role="status" aria-live="polite" className={styles.count}>
        {page.results.length} result{page.results.length === 1 ? "" : "s"}
      </p>
      <div className={styles.list}>
        {page.results.map((result) => (
          <RetrievalResultCard key={result.context.contextId} result={result} />
        ))}
      </div>
    </div>
  );
}
