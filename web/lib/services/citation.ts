import type { RetrievalContext } from "@/lib/domain/retrieval";

function pageRange(first: number, last: number): string {
  return first === last ? `p. ${first}` : `pp. ${first}-${last}`;
}

function periodYear(periodEnd: string | null): string | null {
  if (!periodEnd) return null;
  const year = periodEnd.slice(0, 4);
  return /^\d{4}$/.test(year) ? year : null;
}

/**
 * Server-side citation-label formatter -- the only place a
 * `RetrievalCitation.label` string is built, so Milestone 7B.2 (grounded
 * Q&A) can reuse it verbatim rather than re-deriving formatting rules.
 * Examples (from the milestone brief):
 *   "KP2, 2024 report, pp. 43-44"
 *   "KP2, 2023->2024 comparison, later report, pp. 43-44"
 *   "ACT, 2021 report, p. 18"
 */
export function formatCitationLabel(context: RetrievalContext): string {
  const pages = pageRange(context.firstPageNumber, context.lastPageNumber);

  if (context.contextType === "REPORT_ONLY" || !context.reportSide) {
    const year = periodYear(context.reportPeriodEnd);
    return year
      ? `${context.companyTicker}, ${year} report, ${pages}`
      : `${context.companyTicker}, ${pages}`;
  }

  const earlierYear = periodYear(context.earlierPeriodEnd);
  const laterYear = periodYear(context.laterPeriodEnd);
  const sideLabel = context.reportSide === "EARLIER" ? "earlier report" : "later report";

  if (earlierYear && laterYear) {
    return `${context.companyTicker}, ${earlierYear}->${laterYear} comparison, ${sideLabel}, ${pages}`;
  }
  return `${context.companyTicker}, ${sideLabel}, ${pages}`;
}
