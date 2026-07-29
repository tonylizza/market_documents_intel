import type { CompanyHistoricalHighlights, CompanyMetricPoint } from "@/lib/domain/company";
import type { ComparisonPreview, ComparisonSummary } from "@/lib/domain/comparison";
import { COMPARISON_METRICS, resolveComparisonMetricKey, type ComparisonMetricKey } from "@/lib/config/comparison";
import { buildFindings } from "@/lib/content/finding-copy";
import { buildHeadlineMetrics } from "@/lib/services/headline-metrics";

/** Field accessors for each approved metric key -- the single point of
 * truth mapping a `ComparisonMetricKey` to its `value`/`label` pair on
 * `ComparisonSummary`. Kept alongside (not inside) `lib/config/comparison.ts`
 * since it's a data-shaping function, not configuration. */
const METRIC_ACCESSORS: Record<
  ComparisonMetricKey,
  { value: (c: ComparisonSummary) => number | null; label: (c: ComparisonSummary) => string | null }
> = {
  disclosure_change: { value: (c) => c.disclosureChangeScore, label: (c) => c.disclosureChangeLabel },
  uncertainty_change: { value: (c) => c.uncertaintyChange, label: (c) => c.uncertaintyChangeLabel },
  net_tone_change: { value: (c) => c.netToneChange, label: (c) => c.netToneChangeLabel },
  risk_introduction: { value: (c) => c.riskIntroductionRate, label: (c) => c.riskIntroductionLabel },
  risk_removal: { value: (c) => c.riskRemovalRate, label: (c) => c.riskRemovalLabel },
  governance_change: { value: (c) => c.governanceChange, label: (c) => c.governanceChangeLabel },
  financial_condition_change: { value: (c) => c.financialConditionChange, label: (c) => c.financialConditionChangeLabel },
};

/**
 * Extracts one metric's series from an already-fetched comparison history --
 * a pure, zero-query function (no per-metric database round trip). A `null`
 * `value` is preserved as a genuine gap in the series, never coerced to
 * `0`.
 */
export function getCompanyMetricSeries(
  comparisons: readonly ComparisonSummary[],
  metricKeyInput: string | null | undefined,
): CompanyMetricPoint[] {
  const metricKey = resolveComparisonMetricKey(metricKeyInput);
  const accessor = METRIC_ACCESSORS[metricKey];
  return comparisons.map((comparison) => ({
    comparisonId: comparison.id,
    earlierPeriodEnd: comparison.earlierPeriodEnd,
    laterPeriodEnd: comparison.laterPeriodEnd,
    value: accessor.value(comparison),
    label: accessor.label(comparison),
    isIrregularGap: comparison.isIrregularGap,
    isTransition: comparison.isTransition,
    isHistoricalPeakChange: comparison.isHistoricalPeakChange,
  }));
}

export { COMPARISON_METRICS };

/**
 * Corpus-relative navigator shortcuts for range-filtered (>20 comparisons)
 * mode. "Largest eligible" means `*PrimaryEligible === true`, not merely
 * "largest magnitude regardless of quality" -- a review-qualified value is
 * never surfaced as a confirmed shortcut destination.
 */
export function getCompanyHistoricalHighlights(comparisons: readonly ComparisonSummary[]): CompanyHistoricalHighlights {
  const latest = comparisons.find((c) => c.isLatestForCompany) ?? null;
  const historicalPeak = comparisons.find((c) => c.isHistoricalPeakChange) ?? null;

  const eligibleUncertaintyIncreases = comparisons.filter(
    (c) => c.reportSidePrimaryEligible === true && c.uncertaintyChange !== null && c.uncertaintyChange > 0,
  );
  const largestUncertaintyIncrease = eligibleUncertaintyIncreases.reduce<ComparisonSummary | null>((best, c) => {
    if (!best) return c;
    return (c.uncertaintyChange ?? 0) > (best.uncertaintyChange ?? 0) ? c : best;
  }, null);

  const eligibleRiskIntroductions = comparisons.filter(
    (c) => c.alignmentChangePrimaryEligible === true && c.riskIntroductionRate !== null && c.riskIntroductionRate > 0,
  );
  const largestRiskIntroduction = eligibleRiskIntroductions.reduce<ComparisonSummary | null>((best, c) => {
    if (!best) return c;
    return (c.riskIntroductionRate ?? 0) > (best.riskIntroductionRate ?? 0) ? c : best;
  }, null);

  return {
    latestComparisonId: latest?.id ?? null,
    historicalPeakChangeComparisonId: historicalPeak?.id ?? null,
    largestEligibleUncertaintyIncreaseComparisonId: largestUncertaintyIncrease?.id ?? null,
    largestEligibleRiskIntroductionComparisonId: largestRiskIntroduction?.id ?? null,
  };
}

/**
 * Resolves `?comparison=<id>` against a company's history: missing selects
 * the latest comparison; an id that doesn't belong to this company falls
 * back to the latest comparison too (never crashes, never silently shows
 * another company's data). `null` only when the company has zero
 * comparisons at all.
 */
export function resolveSelectedComparison(
  comparisons: readonly ComparisonSummary[],
  comparisonIdParam: string | null | undefined,
): ComparisonSummary | null {
  if (comparisonIdParam) {
    const requested = comparisons.find((c) => c.id === comparisonIdParam);
    if (requested) return requested;
  }
  return comparisons.find((c) => c.isLatestForCompany) ?? comparisons[comparisons.length - 1] ?? null;
}

export function buildComparisonPreview(comparison: ComparisonSummary): ComparisonPreview {
  return {
    comparison,
    findings: buildFindings(comparison),
    headlineMetrics: buildHeadlineMetrics(comparison),
  };
}
