/**
 * Quality is tracked along three independent dimensions, each with its own
 * plain-language vocabulary (Python-owned, persisted directly on
 * `app.report_comparisons` as `<dimension>_quality_label`). This module
 * only defines the *shape* of that data and the dimension-keyed visual
 * variant (color/icon) the frontend owns -- never a second copy of the
 * text-label translation as primary source; see `formatting/labels.ts` for
 * the narrow, dimension-keyed fallback used only when a label is missing.
 */

export type QualityDimension = "report-side" | "alignment-change" | "disclosure-change";

export type RawQuality = "GOOD" | "USABLE" | "NEEDS_REVIEW" | "FAILED";

export type QualityVisualVariant = "good" | "usable" | "needs-review" | "failed" | "unknown";

export interface QualityInfo {
  dimension: QualityDimension;
  /** Raw upstream quality tier, verbatim -- `null` when not computed for this row. */
  raw: RawQuality | null;
  /** Plain-language label, normally read directly from the database. */
  label: string | null;
}

const KNOWN_RAW_QUALITIES: ReadonlySet<string> = new Set(["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"]);

export function isRawQuality(value: string | null | undefined): value is RawQuality {
  return typeof value === "string" && KNOWN_RAW_QUALITIES.has(value);
}

/** Visual severity variant for a raw quality tier -- dimension-independent
 * (all three dimensions use the same four-tier color treatment), but kept
 * as a named function (not inlined in the component) so it stays a single
 * point of truth and is independently unit-testable. */
export function qualityVisualVariant(raw: RawQuality | null): QualityVisualVariant {
  switch (raw) {
    case "GOOD":
      return "good";
    case "USABLE":
      return "usable";
    case "NEEDS_REVIEW":
      return "needs-review";
    case "FAILED":
      return "failed";
    default:
      return "unknown";
  }
}

export const QUALITY_DIMENSION_DISPLAY_NAMES: Record<QualityDimension, string> = {
  "report-side": "Report-side quality",
  "alignment-change": "Alignment-change quality",
  "disclosure-change": "Disclosure-change quality",
};

/** Best-to-worst ordinal ranking, dimension-independent -- used only for
 * "at least this good" comparisons (e.g. a discovery minimum-quality
 * filter), never for display. */
export const QUALITY_TIER_ORDER: Record<RawQuality, number> = {
  FAILED: 0,
  NEEDS_REVIEW: 1,
  USABLE: 2,
  GOOD: 3,
};

/** `true` when `raw` is at least as good as `minimum` (or when no minimum
 * is set at all). A `null` `raw` never satisfies a set minimum -- an
 * unknown/unscored row is not assumed to pass a quality bar. */
export function meetsMinimumQuality(raw: RawQuality | null, minimum: RawQuality | null): boolean {
  if (!minimum) return true;
  if (!raw) return false;
  return QUALITY_TIER_ORDER[raw] >= QUALITY_TIER_ORDER[minimum];
}
