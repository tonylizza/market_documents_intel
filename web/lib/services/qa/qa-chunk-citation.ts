import type { QaChunkCitation } from "@/lib/domain/qa-chunk";

function pageRange(first: number, last: number): string {
  return first === last ? `p. ${first}` : `pp. ${first}-${last}`;
}

function periodYear(periodEnd: string | null): string | null {
  if (!periodEnd) return null;
  const year = periodEnd.slice(0, 4);
  return /^\d{4}$/.test(year) ? year : null;
}

/**
 * Server-side citation-label formatter for `/ask` -- mirrors
 * `lib/services/citation.ts::formatCitationLabel`'s format exactly
 * ("KP2, 2024 report, pp. 12-14") so citations read consistently whether
 * they came from `/passages` or `/ask`, but built from `QaChunkCitation`'s
 * report-only shape (a chunk never carries comparison-side information --
 * that is resolved separately by `question-router.ts`'s `COMPARISON_QA`
 * path when applicable).
 */
export function formatQaChunkCitationLabel(citation: QaChunkCitation): string {
  const pages = pageRange(citation.pageStart, citation.pageEnd);
  const year = periodYear(citation.reportPeriodEnd);
  return year
    ? `${citation.companyTicker}, ${year} report, ${pages}`
    : `${citation.companyTicker}, ${pages}`;
}
