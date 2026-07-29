import type { PaginationState } from "@/lib/domain/passage";

/** Shared pagination-state builder for both `/passages` and
 * `/comparisons/[id]/evidence` -- a requested `page` beyond the last real
 * page is normalized down to `totalPages` (never an out-of-range page
 * silently rendered as valid), never re-queried. */
export function buildPaginationState(page: number, pageSize: number, totalCount: number): PaginationState {
  const totalPages = totalCount > 0 ? Math.ceil(totalCount / pageSize) : 0;
  const normalizedPage = totalPages > 0 ? Math.min(Math.max(page, 1), totalPages) : 1;
  return {
    page: normalizedPage,
    pageSize,
    totalCount,
    totalIsCapped: false,
    totalPages,
    hasNextPage: normalizedPage < totalPages,
    hasPreviousPage: normalizedPage > 1,
  };
}
