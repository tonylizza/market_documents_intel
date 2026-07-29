import Link from "next/link";
import type { PaginationState } from "@/lib/domain/passage";
import styles from "./PaginationNav.module.css";

export interface PaginationNavProps {
  pagination: PaginationState;
  /** Builds the href for a given page number -- callers own their own
   * query-string serialization (`/passages` vs. `/comparisons/.../evidence`
   * use different param sets), this component only owns page-number logic. */
  buildHref: (page: number) => string;
  label?: string;
}

const MAX_VISIBLE_PAGE_LINKS = 7;

/** Compact numbered range around the current page (never every page for a
 * large result set) -- e.g. `1 … 4 5 [6] 7 8 … 42`. */
function buildPageRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= MAX_VISIBLE_PAGE_LINKS) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }
  const pages = new Set<number>([1, total, current]);
  for (let offset = 1; offset <= 2; offset += 1) {
    if (current - offset >= 1) pages.add(current - offset);
    if (current + offset <= total) pages.add(current + offset);
  }
  const sorted = Array.from(pages).sort((a, b) => a - b);
  const result: (number | "ellipsis")[] = [];
  for (let i = 0; i < sorted.length; i += 1) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push("ellipsis");
    result.push(sorted[i]);
  }
  return result;
}

/** Accessible, server-rendered (real `<a>` links, no client JS required)
 * page navigation -- works with the existing `<Link>`-based routing/URL
 * state everywhere in this app. */
export function PaginationNav({ pagination, buildHref, label = "Results pagination" }: PaginationNavProps) {
  if (pagination.totalPages <= 1) return null;

  const range = buildPageRange(pagination.page, pagination.totalPages);

  return (
    <nav aria-label={label} className={styles.nav}>
      <Link
        href={buildHref(pagination.page - 1)}
        aria-disabled={!pagination.hasPreviousPage}
        className={`${styles.link} ${!pagination.hasPreviousPage ? styles.disabled : ""}`}
        aria-label="Previous page"
        tabIndex={pagination.hasPreviousPage ? undefined : -1}
      >
        ← Previous
      </Link>

      <ul className={styles.pages}>
        {range.map((entry, index) =>
          entry === "ellipsis" ? (
            <li key={`ellipsis-${index}`} aria-hidden="true" className={styles.ellipsis}>
              …
            </li>
          ) : (
            <li key={entry}>
              <Link
                href={buildHref(entry)}
                aria-current={entry === pagination.page ? "page" : undefined}
                className={`${styles.pageLink} ${entry === pagination.page ? styles.currentPage : ""}`}
                aria-label={`Page ${entry}`}
              >
                {entry}
              </Link>
            </li>
          ),
        )}
      </ul>

      <Link
        href={buildHref(pagination.page + 1)}
        aria-disabled={!pagination.hasNextPage}
        className={`${styles.link} ${!pagination.hasNextPage ? styles.disabled : ""}`}
        aria-label="Next page"
        tabIndex={pagination.hasNextPage ? undefined : -1}
      >
        Next →
      </Link>
    </nav>
  );
}
