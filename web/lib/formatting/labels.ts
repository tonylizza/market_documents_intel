import type { QualityDimension, RawQuality } from "@/lib/domain/quality";

/**
 * Dimension-keyed fallback label vocabulary -- mirrors
 * `market_documents.publishing.labels` on the Python side exactly. Used
 * ONLY when a row's `<dimension>_quality_label` is missing/null but its raw
 * quality tier is present (defensive tolerance for a malformed/incomplete
 * row); the database-supplied label is always preferred when present. Kept
 * as three distinct maps -- never collapsed into one generic
 * tier-to-text lookup -- so a report-side "NEEDS_REVIEW" and an
 * alignment-change "NEEDS_REVIEW" can never be shown with the wrong
 * dimension's wording.
 */
const REPORT_SIDE_LABELS: Record<RawQuality, string> = {
  GOOD: "Analysis ready",
  USABLE: "Ready with caution",
  NEEDS_REVIEW: "Review recommended",
  FAILED: "Unavailable",
};

const ALIGNMENT_CHANGE_LABELS: Record<RawQuality, string> = {
  GOOD: "Strong attribution",
  USABLE: "Usable attribution",
  NEEDS_REVIEW: "Attribution uncertain",
  FAILED: "Attribution unavailable",
};

// Disclosure-change quality reuses the report-side (generic) vocabulary --
// mirrors `GENERIC_QUALITY_LABELS = REPORT_SIDE_QUALITY_LABELS` in the
// Python `labels` module.
const DISCLOSURE_CHANGE_LABELS: Record<RawQuality, string> = REPORT_SIDE_LABELS;

const LABELS_BY_DIMENSION: Record<QualityDimension, Record<RawQuality, string>> = {
  "report-side": REPORT_SIDE_LABELS,
  "alignment-change": ALIGNMENT_CHANGE_LABELS,
  "disclosure-change": DISCLOSURE_CHANGE_LABELS,
};

/**
 * Resolve the label to display: the database-supplied label when present,
 * otherwise the dimension-keyed fallback for a known raw tier, otherwise
 * `null` (never fabricate text for a row with neither).
 */
export function resolveQualityLabel(
  dimension: QualityDimension,
  raw: RawQuality | null,
  label: string | null,
): string | null {
  if (label) return label;
  if (!raw) return null;
  return LABELS_BY_DIMENSION[dimension][raw];
}

/** Reverse lookup: which raw tier does this dimension's display label
 * correspond to? Used only by the `/discover` minimum-quality filter, which
 * has only `discovery_items.quality_label` (text) to work with, not a raw
 * tier column -- `null` for a label that doesn't match this dimension's
 * known vocabulary (never guessed). */
export function rawQualityFromLabel(dimension: QualityDimension, label: string): RawQuality | null {
  const map = LABELS_BY_DIMENSION[dimension];
  const match = (Object.keys(map) as RawQuality[]).find((tier) => map[tier] === label);
  return match ?? null;
}

const PASSAGE_STATUS_LABELS: Record<string, string> = {
  NEW: "New",
  REMOVED: "Removed",
  SUBSTANTIALLY_MODIFIED: "Substantially modified",
  LIGHTLY_MODIFIED: "Lightly modified",
  UNCHANGED: "Unchanged",
  AMBIGUOUS: "Ambiguous",
};

export function formatPassageStatusLabel(status: string): string {
  return PASSAGE_STATUS_LABELS[status] ?? status;
}

const CATEGORY_LABEL_OVERRIDES: Record<string, string> = {
  financial_condition: "Financial condition",
  strong_modal: "Strong modal",
  weak_modal: "Weak modal",
};

/** `category`/`subcategory` values are lower_snake_case dictionary/taxonomy
 * keys (e.g. `financial_condition`, `strong_modal`) -- never shown raw to
 * the user. */
export function formatCategoryLabel(category: string): string {
  if (CATEGORY_LABEL_OVERRIDES[category]) return CATEGORY_LABEL_OVERRIDES[category];
  return category
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/** Plain-language coverage note for the company header -- assembled from
 * already-fetched counts/dates, never a second database query. */
export function buildDataCoverageNote(
  reportCount: number,
  comparisonCount: number,
  firstReportPeriodEnd: string | null,
  latestReportPeriodEnd: string | null,
): string {
  const reportWord = reportCount === 1 ? "report" : "reports";
  const comparisonWord = comparisonCount === 1 ? "comparison" : "comparisons";
  if (!firstReportPeriodEnd || !latestReportPeriodEnd) {
    return `Coverage: ${reportCount} ${reportWord}, ${comparisonCount} ${comparisonWord}.`;
  }
  return `Coverage spans ${firstReportPeriodEnd.slice(0, 4)}–${latestReportPeriodEnd.slice(0, 4)} across ${reportCount} ${reportWord} and ${comparisonCount} ${comparisonWord}.`;
}
