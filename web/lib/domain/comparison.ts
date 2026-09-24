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
  /** Track 7F.4 M3 -- the Discover ranking/materiality metric (|M3| >= 0.04).
   * `financialConditionChange` above (M1) is descriptive context only. */
  financialConditionShareChange: number | null;
  financialConditionShareChangeLabel: string | null;
  /** Track 7F.4 M6b -- supporting detail only, never a signed label. */
  financialConditionTopicMixChange: number | null;
  /** Track 7F.7a.1 M3-G -- the Discover ranking/materiality metric
   * (|M3-G| >= 0.05). `governanceChange` above (M1-G) is descriptive
   * context only. */
  governanceShareChange: number | null;
  governanceShareChangeLabel: string | null;
  /** Track 7F.7a.1a -- governance's share of classified disclosure, each
   * side, for the factual count/share decomposition (`governanceShareEarlier
   * = governanceHitsEarlier / customTaxonomyHitsEarlier`). */
  governanceShareEarlier: number | null;
  governanceShareLater: number | null;
  /** Track 7F.7a.1 M6-G -- supporting detail only, never a signed label. */
  governanceTopicMixChange: number | null;
  /** Track 7F.7a.1a -- raw counts behind M3-G's share ratio
   * (`governanceShareChange = governanceHits / customTaxonomyHits`), for
   * the factual count/share decomposition in governance supporting detail.
   * Never a fabricated 0 -- `null` only when not computed (no language
   * signal run for this side). */
  governanceHitsEarlier: number | null;
  governanceHitsLater: number | null;
  customTaxonomyHitsEarlier: number | null;
  customTaxonomyHitsLater: number | null;

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
  /** Track 7F.9 -- unified topic-change decomposition and net-tone
   * components. `null` when the comparison has no published language
   * features (or was built before the 7F.9 publication). */
  topicChange: TopicChangeDetail | null;
}

/** Track 7F.9 -- one category's C_min topic-change record, published
 * verbatim from `app.current_report_comparisons`. `densityChange` is the
 * existing M1 column. The four diagnostics are supporting detail only and
 * never an eligibility condition. */
export interface TopicCategoryChange {
  hitsEarlier: number | null;
  hitsLater: number | null;
  countChangePer1000: number | null;
  densityChange: number | null;
  topicChange: number | null;
  supportingHits: number | null;
  opposingHits: number | null;
  changeConsistencyRatio: number | null;
  largestPassageShare: number | null;
}

export type TopicCategory = "financial_condition" | "governance" | "uncertainty";

export const TOPIC_CATEGORIES: readonly TopicCategory[] = ["financial_condition", "governance", "uncertainty"];

/** Track 7F.9 -- one of the highest-hit passages for a topic category on one
 * report side (eligible narrative only). Evidence is report-side on
 * purpose: a passage is shown because *its own report* contains the
 * category's words, never as a claimed earlier->later causal pair. */
export interface TopicEvidencePassage {
  category: TopicCategory;
  reportSide: "EARLIER" | "LATER";
  passageComparisonId: string;
  hits: number;
  heading: string | null;
  excerpt: string;
  firstPageNumber: number | null;
  alignmentStatus: string;
  confidence: string;
  /** Non-null when the passage's alignment is too weak to read its
   * NEW/REMOVED/SUBSTANTIALLY_MODIFIED status as definitive. */
  alignmentCaveat: string | null;
}

export interface TopicChangeDetail {
  wordsEarlier: number | null;
  wordsLater: number | null;
  categories: Record<TopicCategory, TopicCategoryChange>;
  /** Net-tone components: `netToneChange = positiveRateChange -
   * negativeRateChange` (per 1,000 words). */
  positiveRateChange: number | null;
  negativeRateChange: number | null;
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
  /** Raw hit counts -- populated for Track 7F.4's financial_condition
   * subcategory-mover rows (`population === "financial_condition_
   * subcategory"`), which have no meaningful per-1000-word rate. `null` for
   * every other report_side/alignment_change row. */
  earlierCount: number | null;
  laterCount: number | null;
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
