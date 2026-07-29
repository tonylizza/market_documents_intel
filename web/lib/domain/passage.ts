import type { RawQuality } from "@/lib/domain/quality";

export type AlignmentStatus =
  | "NEW"
  | "REMOVED"
  | "UNCHANGED"
  | "LIGHTLY_MODIFIED"
  | "SUBSTANTIALLY_MODIFIED"
  | "AMBIGUOUS";

export type AlignmentType = "ONE_TO_ONE" | "UNMATCHED_LATER" | "UNMATCHED_EARLIER";

export type Confidence = "HIGH" | "MEDIUM" | "LOW" | "NEEDS_REVIEW";

export type PassageType = "HEADING_WITH_BODY" | "MULTI_PARAGRAPH" | "PARAGRAPH" | "LIST" | "TABLE_CONTEXT";

export type ReportSide = "EARLIER" | "LATER";

/** Real, non-null `app.current_passages.structured_content_category` values
 * observed in the live corpus -- a `null` category (the overwhelming
 * majority of passages) means "ordinary narrative text", not "unknown". */
export type StructuredContentCategory =
  | "list_content"
  | "numeric_or_table_like_source"
  | "contents_or_index_like"
  | "financial_table_rendered_as_prose"
  | "ordinary_prose_false_positive"
  | "legitimate_short_abbreviation"
  | "caption_or_label_like"
  | "table_context"
  | "currency_exposure_table_mixed";

/** One `text` span produced by TypeScript-side lexical highlighting -- a
 * structured alternative to raw HTML injection. `matched` spans are
 * rendered as `<mark>`; a component never receives a pre-built HTML string. */
export interface HighlightSpan {
  text: string;
  matched: boolean;
}

/** One `/passages` search-result row. A passage without any published
 * alignment (`passageComparisonId === null`) is a genuine, valid result --
 * "a report-only passage" -- never hidden or treated as an error. */
export interface PassageSearchResult {
  passageId: string;
  passageComparisonId: string | null;
  reportComparisonId: string | null;
  companyId: string;
  companyTicker: string;
  companyName: string;
  reportId: string;
  reportPeriodEnd: string | null;
  /** `null` when no published alignment exists for this passage. */
  reportSide: ReportSide | null;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  heading: string | null;
  headingHighlight: HighlightSpan[] | null;
  passageType: PassageType;
  structuredContentCategory: StructuredContentCategory | null;
  firstPageNumber: number;
  lastPageNumber: number;
  wordCount: number;
  primaryNarrativeEligible: boolean;
  featureEligible: boolean;
  excerpt: HighlightSpan[];
  alignmentStatus: AlignmentStatus | null;
  alignmentType: AlignmentType | null;
  confidence: Confidence | null;
  confidenceLabel: string | null;
  collisionFlag: boolean | null;
  splitMergeFlag: boolean | null;
  /** Postgres `ts_rank` value, `null` for a filters-only (no lexical query) search. */
  rank: number | null;
}

export type PassageSortKey = "relevance" | "newest_report" | "oldest_report" | "company" | "page_order";

export const PASSAGE_SORT_KEYS: readonly PassageSortKey[] = [
  "relevance",
  "newest_report",
  "oldest_report",
  "company",
  "page_order",
];

export const DEFAULT_PASSAGE_PAGE_SIZE = 25;
export const MAX_PASSAGE_PAGE_SIZE = 50;
export const MAX_PASSAGE_QUERY_LENGTH = 200;
/** A page-count safety cap on the exact `COUNT(*)`, not the result set
 * itself -- pagination always uses `LIMIT`/`OFFSET`, this only bounds how
 * high a displayed "N results" total is allowed to climb before switching
 * to a capped "1,000+ results" presentation. */
export const MAX_COUNTED_PASSAGE_RESULTS = 1000;

/** Fully validated, canonicalized search input -- the only shape the
 * repository/service layer accepts. Built by `parsePassageSearchParams`
 * from raw, untrusted `URLSearchParams`; never constructed from a raw
 * request object directly. */
export interface PassageSearchParams {
  query: string | null;
  exactPhrase: boolean;
  company: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  comparisonId: string | null;
  reportSide: ReportSide | null;
  alignmentStatus: AlignmentStatus | null;
  confidence: Confidence | null;
  passageType: PassageType | null;
  category: string | null;
  subcategory: string | null;
  reportSideQuality: RawQuality | null;
  alignmentChangeQuality: RawQuality | null;
  primaryNarrativeEligible: boolean | null;
  featureEligible: boolean | null;
  irregularGapComparison: boolean | null;
  collisionFlag: boolean | null;
  splitMergeFlag: boolean | null;
  sort: PassageSortKey;
  page: number;
  pageSize: number;
}

export interface PaginationState {
  page: number;
  pageSize: number;
  /** Exact when `totalCount <= MAX_COUNTED_PASSAGE_RESULTS`, otherwise a
   * capped lower bound -- see `totalIsCapped`. */
  totalCount: number;
  totalIsCapped: boolean;
  totalPages: number;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
}

export interface PassageSearchPage {
  results: PassageSearchResult[];
  pagination: PaginationState;
  params: PassageSearchParams;
}

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

/** Distinct, real values available to populate `/passages` filter controls
 * -- never a hardcoded/invented list. `categories` includes only category
 * values with at least one published signal row; `subcategoriesByCategory`
 * is similarly real-data-derived (a category with no subcategories, e.g.
 * `constraining`, is simply absent as a key). */
export interface PassageFilterOptions {
  companies: FilterOption[];
  alignmentStatuses: FilterOption[];
  confidenceLevels: FilterOption[];
  passageTypes: FilterOption[];
  categories: FilterOption[];
  subcategoriesByCategory: Record<string, FilterOption[]>;
  reportSideQualities: FilterOption[];
  alignmentChangeQualities: FilterOption[];
}

/** Header + status-bucket counts for `/comparisons/[comparisonId]/evidence`.
 * `header` reuses the same fields already available on `ReportComparisonDetail`
 * -- deliberately not a second, narrower type. */
export interface ComparisonEvidenceSummary {
  comparisonId: string;
  companyId: string;
  companyTicker: string;
  companyName: string;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  gapMonths: number;
  reportSideQuality: RawQuality | null;
  reportSideQualityLabel: string | null;
  alignmentChangeQuality: RawQuality | null;
  alignmentChangeQualityLabel: string | null;
  counts: Record<AlignmentStatus, number>;
  totalCount: number;
}

export interface ComparisonEvidenceFilters {
  status: AlignmentStatus | "ALL";
  confidence: Confidence | null;
  category: string | null;
  subcategory: string | null;
  collisionFlag: boolean | null;
  splitMergeFlag: boolean | null;
  hasHeading: boolean | null;
  pageStart: number | null;
  pageEnd: number | null;
  page: number;
  pageSize: number;
}

export interface PassageSideExcerpt {
  passageId: string;
  heading: string | null;
  excerpt: HighlightSpan[];
  firstPageNumber: number;
  lastPageNumber: number;
  wordCount: number;
}

export interface ComparisonEvidenceItem {
  passageComparisonId: string;
  alignmentStatus: AlignmentStatus;
  alignmentType: AlignmentType;
  confidence: Confidence;
  confidenceLabel: string;
  collisionFlag: boolean;
  splitMergeFlag: boolean;
  contentScore: number | null;
  earlier: PassageSideExcerpt | null;
  later: PassageSideExcerpt | null;
}

export interface ComparisonEvidencePage {
  items: ComparisonEvidenceItem[];
  pagination: PaginationState;
}

export interface ComparisonEvidenceFilterOptions {
  confidenceLevels: FilterOption[];
  categories: FilterOption[];
  subcategoriesByCategory: Record<string, FilterOption[]>;
}

/** One side (earlier or later) of a matched/one-sided passage comparison --
 * full, uncapped published text, never truncated (see milestone: "Do not
 * truncate the full published text on the detail page"). `null` means this
 * side genuinely has no aligned passage (NEW/REMOVED/one-sided AMBIGUOUS),
 * never a fabricated placeholder. */
export interface PassageSideDetail {
  passageId: string;
  heading: string | null;
  text: string;
  wordCount: number;
  firstPageNumber: number;
  lastPageNumber: number;
  passageType: PassageType;
  structuredContentCategory: StructuredContentCategory | null;
  primaryNarrativeEligible: boolean;
  featureEligible: boolean;
}

export interface PassageComparisonDetail {
  passageComparisonId: string;
  reportComparisonId: string;
  companyId: string;
  companyTicker: string;
  companyName: string;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  alignmentStatus: AlignmentStatus;
  alignmentType: AlignmentType;
  confidence: Confidence;
  confidenceLabel: string;
  contentScore: number | null;
  semanticSimilarity: number | null;
  lexicalSimilarity: number | null;
  headingSimilarity: number | null;
  positionDifference: number | null;
  collisionFlag: boolean;
  splitMergeFlag: boolean;
  reviewReason: string | null;
  earlier: PassageSideDetail | null;
  later: PassageSideDetail | null;
}

/** One `app.current_passage_language_signals` row, grouped for display by
 * `reportSide` -- `subcategory === null` is a real core-category row
 * (constraining/litigious/negative/positive/strong_modal/uncertainty/
 * weak_modal), not a missing value. */
export interface PassageLanguageSignal {
  reportSide: ReportSide;
  category: string;
  subcategory: string | null;
  rawCount: number;
  negatedCount: number | null;
  adjustedCount: number | null;
  ratePer1000: number | null;
  isIntroduced: boolean | null;
  isRemoved: boolean | null;
  isRetained: boolean | null;
}

export type TextDiffOp = "equal" | "insert" | "delete";

/** One token (or whitespace run) of a deterministic word-level diff --
 * presentation-only, never fed back into any analytical field. */
export interface TextDiffSegment {
  op: TextDiffOp;
  text: string;
}

export interface TextDiffResult {
  earlier: TextDiffSegment[];
  later: TextDiffSegment[];
  /** `true` when both inputs were within `MAX_DIFF_INPUT_LENGTH` and a real
   * token diff was computed; `false` means the fallback (unhighlighted
   * original text) was used instead. */
  diffed: boolean;
}

export const MAX_DIFF_INPUT_LENGTH = 20_000;
export const MAX_EXCERPT_LENGTH = 320;
