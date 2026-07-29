import type { ComparisonSummary, HeadlineMetric } from "@/lib/domain/comparison";
import type { QualityDimension, RawQuality } from "@/lib/domain/quality";
import { formatMetricValue } from "@/lib/formatting/numbers";

/** The six fixed headline metric cards shown on the comparison detail page
 * (and reused for the company page's compact preview) -- deliberately a
 * subset of `COMPARISON_METRIC_KEYS` (excludes `risk_removal`, which is
 * full-history-chart-only) and never a generic/arbitrary set. */
export const HEADLINE_METRIC_KEYS = [
  "disclosure_change",
  "net_tone_change",
  "uncertainty_change",
  "risk_introduction",
  "governance_change",
  "financial_condition_change",
] as const;

export type HeadlineMetricKey = (typeof HEADLINE_METRIC_KEYS)[number];

interface HeadlineMetricSpec {
  key: HeadlineMetricKey;
  displayName: string;
  unit: "score_0_1" | "rate_per_1000_words";
  qualityDimension: QualityDimension;
  explanation: string;
  value: (c: ComparisonSummary) => number | null;
  valueLabel: (c: ComparisonSummary) => string | null;
  quality: (c: ComparisonSummary) => RawQuality | null;
  qualityLabel: (c: ComparisonSummary) => string | null;
  primaryEligible: (c: ComparisonSummary) => boolean | null;
}

const SPECS: Record<HeadlineMetricKey, HeadlineMetricSpec> = {
  disclosure_change: {
    key: "disclosure_change",
    displayName: "Overall disclosure change",
    unit: "score_0_1",
    qualityDimension: "disclosure-change",
    explanation:
      "How much this report's disclosures changed overall compared with the prior report, based on lexical and structural passage-alignment change.",
    value: (c) => c.disclosureChangeScore,
    valueLabel: (c) => c.disclosureChangeLabel,
    quality: (c) => c.disclosureChangeQuality,
    qualityLabel: (c) => c.disclosureChangeQualityLabel,
    primaryEligible: (c) => c.disclosureChangePrimaryEligible,
  },
  net_tone_change: {
    key: "net_tone_change",
    displayName: "Net tone change",
    unit: "rate_per_1000_words",
    qualityDimension: "report-side",
    explanation: "Change in overall language tone (positive minus negative word rate) compared with the prior report.",
    value: (c) => c.netToneChange,
    valueLabel: (c) => c.netToneChangeLabel,
    quality: (c) => c.reportSideQuality,
    qualityLabel: (c) => c.reportSideQualityLabel,
    primaryEligible: (c) => c.reportSidePrimaryEligible,
  },
  uncertainty_change: {
    key: "uncertainty_change",
    displayName: "Uncertainty change",
    unit: "rate_per_1000_words",
    qualityDimension: "report-side",
    explanation: "Change in uncertainty-related language rate compared with the prior report.",
    value: (c) => c.uncertaintyChange,
    valueLabel: (c) => c.uncertaintyChangeLabel,
    quality: (c) => c.reportSideQuality,
    qualityLabel: (c) => c.reportSideQualityLabel,
    primaryEligible: (c) => c.reportSidePrimaryEligible,
  },
  risk_introduction: {
    key: "risk_introduction",
    displayName: "Risk language introduced",
    unit: "rate_per_1000_words",
    qualityDimension: "alignment-change",
    explanation: "Risk-related language introduced in passages that are new or substantially changed since the prior report.",
    value: (c) => c.riskIntroductionRate,
    valueLabel: (c) => c.riskIntroductionLabel,
    quality: (c) => c.alignmentChangeQuality,
    qualityLabel: (c) => c.alignmentChangeQualityLabel,
    primaryEligible: (c) => c.alignmentChangePrimaryEligible,
  },
  governance_change: {
    key: "governance_change",
    displayName: "Governance-language change",
    unit: "rate_per_1000_words",
    qualityDimension: "report-side",
    explanation: "Change in governance-related language rate compared with the prior report.",
    value: (c) => c.governanceChange,
    valueLabel: (c) => c.governanceChangeLabel,
    quality: (c) => c.reportSideQuality,
    qualityLabel: (c) => c.reportSideQualityLabel,
    primaryEligible: (c) => c.reportSidePrimaryEligible,
  },
  financial_condition_change: {
    key: "financial_condition_change",
    displayName: "Financial-condition change",
    unit: "rate_per_1000_words",
    qualityDimension: "report-side",
    explanation: "Change in language describing financial condition compared with the prior report.",
    value: (c) => c.financialConditionChange,
    valueLabel: (c) => c.financialConditionChangeLabel,
    quality: (c) => c.reportSideQuality,
    qualityLabel: (c) => c.reportSideQualityLabel,
    primaryEligible: (c) => c.reportSidePrimaryEligible,
  },
};

/** Builds the six fixed headline metric cards from an already-fetched
 * `ComparisonSummary` -- zero additional queries. `reviewQualifiedExploratory`
 * is derived from `primaryEligible` (never a hardcoded corpus assumption),
 * so it tracks a future publication where disclosure-change quality
 * improves without a code change. */
export function buildHeadlineMetrics(comparison: ComparisonSummary): HeadlineMetric[] {
  return HEADLINE_METRIC_KEYS.map((key) => {
    const spec = SPECS[key];
    const value = spec.value(comparison);
    return {
      metricKey: spec.key,
      displayName: spec.displayName,
      value,
      valueDisplay: spec.valueLabel(comparison) ?? formatMetricValue(value, spec.unit),
      unit: spec.unit,
      quality: spec.quality(comparison),
      qualityLabel: spec.qualityLabel(comparison),
      qualityDimension: spec.qualityDimension,
      primaryEligible: spec.primaryEligible(comparison),
      explanation: spec.explanation,
      reviewQualifiedExploratory: spec.key === "disclosure_change" && spec.primaryEligible(comparison) !== true,
    } satisfies HeadlineMetric;
  });
}
