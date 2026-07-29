import type { ComparisonSummary } from "@/lib/domain/comparison";

/** Shared `ComparisonSummary` builder for 7A.3 unit/component tests --
 * avoids ~40-line object literals repeated across every test file. Every
 * field defaults to a realistic, non-null value so tests only need to
 * override what they're actually asserting on. */
export function makeComparisonSummary(overrides: Partial<ComparisonSummary> = {}): ComparisonSummary {
  return {
    id: "cmp-1",
    companyId: "company-1",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    gapMonths: 12,
    isTransition: false,
    isIrregularGap: false,
    isLatestForCompany: false,
    isHistoricalPeakChange: false,

    disclosureChangeScore: 0.42,
    disclosureChangeLabel: "Moderate change",
    disclosureChangePercentile: 60,
    disclosureChangeQuality: "NEEDS_REVIEW",
    disclosureChangeQualityLabel: "Review recommended",
    disclosureChangePrimaryEligible: false,
    disclosureChangeWarning: "exclusion: feature quality is NEEDS_REVIEW",

    netToneChange: -1.2,
    netToneChangeLabel: "Moderate decrease",
    uncertaintyChange: 1.5,
    uncertaintyChangeLabel: "Moderate increase",
    riskIntroductionRate: 2.1,
    riskIntroductionLabel: "Notable increase",
    riskRemovalRate: 0.3,
    riskRemovalLabel: "Minimal increase",
    governanceChange: 0.4,
    governanceChangeLabel: "Minimal increase",
    financialConditionChange: 0.2,
    financialConditionChangeLabel: "Minimal increase",

    reportSideQuality: "GOOD",
    reportSideQualityLabel: "Analysis ready",
    reportSidePrimaryEligible: true,
    alignmentChangeQuality: "USABLE",
    alignmentChangeQualityLabel: "Usable attribution",
    alignmentChangePrimaryEligible: true,

    primaryFindingKey: "largest_uncertainty_increase",
    secondaryFindingKey: null,
    tertiaryFindingKey: null,
    findingPayload: {
      largest_uncertainty_increase: { value: 1.5, magnitude: 1.5 },
      _disclosure_change_diagnostics: { score_available: true },
    },

    ...overrides,
  };
}

/** Builds `count` consecutive comparisons for one company, chronologically
 * ordered (oldest first, matching `chronological_index` ASC), with
 * distinct ids/periods -- used by adaptive-navigator threshold and
 * synthetic long-history tests. */
export function makeComparisonHistory(count: number, overrides: (index: number) => Partial<ComparisonSummary> = () => ({})): ComparisonSummary[] {
  return Array.from({ length: count }, (_, index) => {
    const laterYear = 2010 + index;
    return makeComparisonSummary({
      id: `cmp-${index}`,
      earlierPeriodEnd: `${laterYear - 1}-06-30`,
      laterPeriodEnd: `${laterYear}-06-30`,
      isLatestForCompany: index === count - 1,
      ...overrides(index),
    });
  });
}
