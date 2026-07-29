import type { QualityDimension, RawQuality } from "@/lib/domain/quality";

/**
 * One `app.current_report_comparisons` row's application-facing fields.
 * Every `*_quality`/`*_label`/`*_primary_eligible` field is read verbatim
 * from the database -- never recomputed. `disclosureChange*` fields may be
 * present (a real score) while `disclosureChangePrimaryEligible` is
 * `false`: a review-qualified value is genuinely displayable, just never a
 * primary finding (see `DisclosureChangeSummary`).
 */
export interface ComparisonSummary {
  id: string;
  companyId: string;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  gapMonths: number;
  isTransition: boolean;
  isIrregularGap: boolean;
  isLatestForCompany: boolean;
  isHistoricalPeakChange: boolean;

  disclosureChangeScore: number | null;
  disclosureChangeLabel: string | null;
  disclosureChangePercentile: number | null;
  disclosureChangeQuality: RawQuality | null;
  disclosureChangeQualityLabel: string | null;
  disclosureChangePrimaryEligible: boolean | null;
  disclosureChangeWarning: string | null;

  netToneChange: number | null;
  netToneChangeLabel: string | null;
  uncertaintyChange: number | null;
  uncertaintyChangeLabel: string | null;
  riskIntroductionRate: number | null;
  riskIntroductionLabel: string | null;
  riskRemovalRate: number | null;
  riskRemovalLabel: string | null;
  governanceChange: number | null;
  governanceChangeLabel: string | null;
  financialConditionChange: number | null;
  financialConditionChangeLabel: string | null;

  reportSideQuality: RawQuality | null;
  reportSideQualityLabel: string | null;
  reportSidePrimaryEligible: boolean | null;
  alignmentChangeQuality: RawQuality | null;
  alignmentChangeQualityLabel: string | null;
  alignmentChangePrimaryEligible: boolean | null;

  primaryFindingKey: string | null;
  secondaryFindingKey: string | null;
  tertiaryFindingKey: string | null;
  /** Raw `finding_payload` JSONB, `null` when not selected by the query
   * (e.g. the home-page card query). Never rendered directly -- only read
   * through `extractFindingPayloadEntry`/`buildDeterministicFinding`. */
  findingPayload: Record<string, unknown> | null;
}

export interface CompanyCardSummary {
  companyId: string;
  ticker: string;
  name: string;
  sector: string | null;
  firstReportPeriodEnd: string | null;
  latestReportPeriodEnd: string | null;
  reportCount: number;
  comparisonCount: number;
  isHistoricalPeak: boolean;
  latestComparison: ComparisonSummary | null;
}

/** One ranked, already primary-eligible language-based discovery item --
 * never one of the two feature-quality-gated types
 * (`largest_overall_change`/`largest_new_disclosure_share`), which are
 * absent from the underlying data by design when review-qualified. */
export interface DiscoveryItemSummary {
  id: string;
  companyId: string;
  companyTicker: string;
  companyName: string;
  reportComparisonId: string;
  discoveryType: string;
  rank: number;
  percentile: number | null;
  supportingValue: number;
  supportingUnit: string;
  qualityLabel: string;
}

/** Alias documenting `ComparisonSummary`'s role as the adaptive navigator's
 * per-item data shape -- deliberately not a duplicate type, since a
 * navigator card needs exactly the fields already on `ComparisonSummary`. */
export type ComparisonNavigatorItem = ComparisonSummary;

/** `/comparisons/[comparisonId]` detail -- one comparison plus the company
 * context needed for the page's header/backlink (`ComparisonSummary
 * .companyId` alone isn't renderable) and the raw quality/warning fields
 * needed to derive `TechnicalQualityDetail` without a second query. */
export interface ReportComparisonDetail extends ComparisonSummary {
  companyTicker: string;
  companyName: string;
  dictionaryMatchRateEarlier: number | null;
  dictionaryMatchRateLater: number | null;
  ambiguousWordShare: number | null;
  collisionFlaggedWordShare: number | null;
  unmatchedWordShare: number | null;
  structuredContentExclusionShare: number | null;
  reportSideWarning: string | null;
  alignmentChangeWarning: string | null;
}

/** One deterministic, published finding rendered via the finding-copy
 * mapping (`lib/content/finding-copy.ts`) -- never regenerated/re-ranked in
 * React. `slot` is which of the (up to) three selected positions this
 * finding occupies; a comparison with fewer than three eligible candidates
 * has fewer `DeterministicFinding` entries, never a placeholder. */
export interface DeterministicFinding {
  key: string;
  slot: "primary" | "secondary" | "tertiary";
  headline: string;
  description: string;
  supportingValue: number | null;
  supportingValueDisplay: string | null;
  supportingUnit: string;
}

/** One of the six fixed headline metric cards on the comparison detail
 * page. `qualityDimension` picks which of the three independent quality
 * vocabularies `quality`/`qualityLabel` belong to. */
export interface HeadlineMetric {
  metricKey: string;
  displayName: string;
  value: number | null;
  valueDisplay: string | null;
  unit: string;
  quality: RawQuality | null;
  qualityLabel: string | null;
  qualityDimension: QualityDimension;
  primaryEligible: boolean | null;
  explanation: string;
  /** True only for `disclosure_change` in the current corpus -- drives the
   * "exploratory, excluded from primary rankings" note. Not a second
   * source of truth for `disclosureChangePrimaryEligible`. */
  reviewQualifiedExploratory: boolean;
}

/** One `app.current_language_metrics` row, report-side or alignment-change
 * scope. `introduced*`/`removed*`/`retainedCount` are only meaningful for
 * `scope === "alignment_change"` (`null` for report-side rows). */
export interface LanguageMetric {
  id: string;
  scope: "report_side" | "alignment_change";
  population: string;
  category: string;
  subcategory: string | null;
  earlierRatePer1000: number | null;
  laterRatePer1000: number | null;
  rateChange: number | null;
  absoluteRateChange: number | null;
  introducedRatePer1000: number | null;
  removedRatePer1000: number | null;
  retainedCount: number | null;
  quality: RawQuality | null;
  primaryEligible: boolean | null;
}

export type PassageCompositionStatus =
  | "NEW"
  | "REMOVED"
  | "SUBSTANTIALLY_MODIFIED"
  | "LIGHTLY_MODIFIED"
  | "UNCHANGED"
  | "AMBIGUOUS";

export interface PassageCompositionBucket {
  status: PassageCompositionStatus;
  count: number;
  /** Share of `totalCount`, `0` when `totalCount` is `0` (never `NaN`). */
  share: number;
}

/** Passage-alignment composition for one comparison, straight from
 * `app.current_passage_comparisons.alignment_status` (a real, directly
 * queryable value for every status including `UNCHANGED` -- never derived
 * from incompatible `report_comparisons` summary-column arithmetic). */
export interface PassageComposition {
  comparisonId: string;
  totalCount: number;
  buckets: PassageCompositionBucket[];
  qualityNote: string;
}

/** Collapsed-by-default technical detail for the comparison page -- raw
 * values already present on `report_comparisons`, never recomputed. */
export interface TechnicalQualityDetail {
  dictionaryMatchRateEarlier: number | null;
  dictionaryMatchRateLater: number | null;
  ambiguousWordShare: number | null;
  collisionFlaggedWordShare: number | null;
  unmatchedWordShare: number | null;
  structuredContentExclusionShare: number | null;
  reportSidePrimaryEligible: boolean | null;
  alignmentChangePrimaryEligible: boolean | null;
  disclosureChangePrimaryEligible: boolean | null;
  reportSideWarning: string | null;
  alignmentChangeWarning: string | null;
  disclosureChangeWarning: string | null;
}

/** Compact preview shown inline on the company page when a comparison is
 * selected -- up to three findings, six headline metrics, and the two
 * quality dimensions that govern the comparison as a whole. */
export interface ComparisonPreview {
  comparison: ComparisonSummary;
  findings: DeterministicFinding[];
  headlineMetrics: HeadlineMetric[];
}
