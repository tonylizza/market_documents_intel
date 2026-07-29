import Link from "next/link";
import type { PassageSearchResult } from "@/lib/domain/passage";
import { HighlightedText } from "@/components/HighlightedText";
import {
  formatAlignmentStatusLabel,
  formatConfidenceLabel,
  formatPassageTypeLabel,
  formatReportSideLabel,
  formatStructuredContentCategoryLabel,
} from "@/lib/config/passage-vocabulary";
import { formatComparisonPeriod, formatPeriodEnd } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./PassageResultCard.module.css";

export interface PassageResultCardProps {
  result: PassageSearchResult;
}

function pageRangeLabel(first: number, last: number): string {
  return first === last ? `Page ${first}` : `Pages ${first}–${last}`;
}

/**
 * One `/passages` search result. A `passageComparisonId === null` result
 * (a report-only passage, no published alignment) renders without any
 * alignment/confidence badge and links to the report period instead of a
 * passage-comparison detail page -- never hidden, never treated as an
 * error (see milestone: "A result may appear without a passage comparison").
 */
export function PassageResultCard({ result }: PassageResultCardProps) {
  const structuredLabel = result.structuredContentCategory
    ? formatStructuredContentCategoryLabel(result.structuredContentCategory)
    : null;

  return (
    <article className={styles.card} aria-labelledby={`result-heading-${result.passageId}-${result.passageComparisonId ?? "none"}`}>
      <div className={styles.meta}>
        <span className={styles.company}>
          {result.companyName} ({result.companyTicker})
        </span>
        <span aria-hidden="true">·</span>
        <span>{formatPeriodEnd(result.reportPeriodEnd) ?? "Period unknown"}</span>
        {result.earlierPeriodEnd && result.laterPeriodEnd && (
          <>
            <span aria-hidden="true">·</span>
            <span>{formatComparisonPeriod(result.earlierPeriodEnd, result.laterPeriodEnd)}</span>
          </>
        )}
        {result.reportSide && (
          <>
            <span aria-hidden="true">·</span>
            <span>{formatReportSideLabel(result.reportSide)}</span>
          </>
        )}
        <span aria-hidden="true">·</span>
        <span>{pageRangeLabel(result.firstPageNumber, result.lastPageNumber)}</span>
      </div>

      <h3 id={`result-heading-${result.passageId}-${result.passageComparisonId ?? "none"}`} className={styles.heading}>
        {result.headingHighlight ? <HighlightedText spans={result.headingHighlight} /> : (result.heading ?? "(No heading)")}
      </h3>

      <p className={styles.excerpt}>
        <HighlightedText spans={result.excerpt} />
      </p>

      <div className={styles.badges}>
        {result.alignmentStatus && <span className={styles.badge}>{formatAlignmentStatusLabel(result.alignmentStatus)}</span>}
        {result.confidence && <span className={styles.badge}>{result.confidenceLabel ?? formatConfidenceLabel(result.confidence)}</span>}
        <span className={styles.badge}>{formatPassageTypeLabel(result.passageType)}</span>
        {structuredLabel && <span className={styles.badge}>{structuredLabel}</span>}
        {result.primaryNarrativeEligible && <span className={styles.badge}>Primary narrative eligible</span>}
        {result.featureEligible && <span className={styles.badge}>Feature eligible</span>}
        {!result.passageComparisonId && <span className={styles.badge}>No published alignment</span>}
      </div>

      <p className={styles.footer}>
        <span>{formatCount(result.wordCount)} words</span>
        {result.passageComparisonId ? (
          <Link href={`/passages/${result.passageComparisonId}`}>View passage evidence →</Link>
        ) : (
          <Link href={`/companies/${result.companyTicker}`}>View company →</Link>
        )}
      </p>
    </article>
  );
}
