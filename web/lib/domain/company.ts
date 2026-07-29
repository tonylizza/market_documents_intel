import type { RawQuality } from "@/lib/domain/quality";
import type { ComparisonSummary } from "@/lib/domain/comparison";

export interface Company {
  id: string;
  ticker: string;
  name: string;
  sector: string | null;
  description: string | null;
  firstReportPeriodEnd: string | null;
  latestReportPeriodEnd: string | null;
  reportCount: number;
  comparisonCount: number;
  latestComparisonId: string | null;
  historicalPeakComparisonId: string | null;
  displayOrder: number;
  hasCurrentData: boolean;
}

/** Company header data for `/companies/[ticker]` -- extends `Company` with
 * the latest report-side quality (never a second quality dimension merged
 * in) and a plain-language coverage note assembled in the service layer,
 * not fabricated in a component. */
export interface CompanyDetail extends Company {
  latestReportSideQuality: RawQuality | null;
  latestReportSideQualityLabel: string | null;
  dataCoverageNote: string;
}

/**
 * Full comparison history for one company, chronological (oldest first).
 * `comparisons` carries every field `ComparisonNavigatorItem`/card/preview
 * rendering needs -- fetched as a single query, never one row per card.
 */
export interface CompanyHistory {
  company: CompanyDetail;
  comparisons: ComparisonSummary[];
}

/** One point on the full-history metric chart -- `value`/`label` already
 * resolved for whichever `ComparisonMetricKey` was selected; `null` value
 * renders as a genuine gap, never a fabricated zero. */
export interface CompanyMetricPoint {
  comparisonId: string;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  value: number | null;
  label: string | null;
  isIrregularGap: boolean;
  isTransition: boolean;
  isHistoricalPeakChange: boolean;
}

/** Corpus-relative highlight comparisons surfaced as navigator shortcuts in
 * range-filtered (>20 comparisons) mode -- each may be `null` when no
 * comparison in the history is eligible (e.g. no primary-eligible
 * uncertainty increase exists yet). */
export interface CompanyHistoricalHighlights {
  latestComparisonId: string | null;
  historicalPeakChangeComparisonId: string | null;
  largestEligibleUncertaintyIncreaseComparisonId: string | null;
  largestEligibleRiskIntroductionComparisonId: string | null;
}
