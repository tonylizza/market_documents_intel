/**
 * Presentation-only thresholds/allowlists for company-history navigation and
 * charting -- deliberately frontend config, not analytical code. Changing a
 * threshold here never changes what data is queried, only how much of it is
 * shown compactly vs. scrollably vs. range-filtered.
 */
export const NAVIGATOR_THRESHOLDS = {
  /** At or below this comparison count, the navigator renders every item in
   * a single compact row. */
  compactMax: 10,
  /** Above `compactMax` and at or below this count, the navigator becomes a
   * horizontally scrollable strip with prev/next controls. */
  scrollableMax: 20,
  /** Above `scrollableMax`, the navigator switches to a full-history chart
   * plus a range-filtered list; this is how many of the most recent
   * comparisons are selected into that range by default. */
  longHistoryWindow: 10,
} as const;

export type NavigatorMode = "compact" | "scrollable" | "range-filtered";

/** Pure function -- the sole point of truth for which navigator mode a given
 * comparison count maps to. Unit-tested directly at both thresholds'
 * boundaries (10/11 and 20/21). */
export function selectNavigatorMode(comparisonCount: number): NavigatorMode {
  if (comparisonCount <= NAVIGATOR_THRESHOLDS.compactMax) return "compact";
  if (comparisonCount <= NAVIGATOR_THRESHOLDS.scrollableMax) return "scrollable";
  return "range-filtered";
}

/**
 * The bounded set of metrics the full-history chart and its selector may
 * show -- deliberately not a generic arbitrary-metric selector. Each key
 * maps to a `ComparisonSummary` field pair (value + precomputed label).
 * `disclosure_change` is the default and the only review-qualified entry in
 * the current corpus; every other metric is report-side or
 * alignment-change, not feature-quality-gated.
 */
export const COMPARISON_METRIC_KEYS = [
  "disclosure_change",
  "uncertainty_change",
  "net_tone_change",
  "risk_introduction",
  "risk_removal",
  "governance_change",
  "financial_condition_change",
] as const;

export type ComparisonMetricKey = (typeof COMPARISON_METRIC_KEYS)[number];

export interface ComparisonMetricConfig {
  key: ComparisonMetricKey;
  displayName: string;
  unit: "score_0_1" | "rate_per_1000_words";
  /** Whether this metric's magnitude is exploratory/review-qualified in the
   * current corpus (only true for `disclosure_change`) -- drives the chart
   * legend/helper note, never a second source of truth for the row's own
   * `disclosureChangeQuality`. */
  reviewQualifiedInCurrentCorpus: boolean;
}

export const COMPARISON_METRICS: Record<ComparisonMetricKey, ComparisonMetricConfig> = {
  disclosure_change: {
    key: "disclosure_change",
    displayName: "Disclosure change",
    unit: "score_0_1",
    reviewQualifiedInCurrentCorpus: true,
  },
  uncertainty_change: {
    key: "uncertainty_change",
    displayName: "Uncertainty change",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
  net_tone_change: {
    key: "net_tone_change",
    displayName: "Net tone change",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
  risk_introduction: {
    key: "risk_introduction",
    displayName: "Risk introduction",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
  risk_removal: {
    key: "risk_removal",
    displayName: "Risk removal",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
  governance_change: {
    key: "governance_change",
    displayName: "Governance change",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
  financial_condition_change: {
    key: "financial_condition_change",
    displayName: "Financial-condition change",
    unit: "rate_per_1000_words",
    reviewQualifiedInCurrentCorpus: false,
  },
};

export const DEFAULT_COMPARISON_METRIC: ComparisonMetricKey = "disclosure_change";

/** Validates an arbitrary (e.g. query-string) value against the approved
 * metric-key allowlist -- never trusts a raw query parameter directly. */
export function isApprovedComparisonMetricKey(value: string | null | undefined): value is ComparisonMetricKey {
  return typeof value === "string" && (COMPARISON_METRIC_KEYS as readonly string[]).includes(value);
}

/** Falls back to the default metric for any unrecognized/missing value --
 * never throws, never renders a blank selector. */
export function resolveComparisonMetricKey(value: string | null | undefined): ComparisonMetricKey {
  return isApprovedComparisonMetricKey(value) ? value : DEFAULT_COMPARISON_METRIC;
}
