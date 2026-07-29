import { describe, expect, it } from "vitest";
import { buildLatestSignalSections, getCompaniesPageViewModel } from "@/lib/services/company-service";
import type { CompanyRepository } from "@/lib/repositories/company-repository";
import type { Company, CompanyDetail, CompanyHistory } from "@/lib/domain/company";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";

function makeSummary(overrides: Partial<ApplicationDataSummary> = {}): ApplicationDataSummary {
  return {
    companyCount: 1,
    reportCount: 2,
    comparisonCount: 1,
    earliestPeriodEnd: "2023-06-30",
    latestPeriodEnd: "2024-06-30",
    publicationNote: "Data reflects the currently active publication.",
    ...overrides,
  };
}

function makeCard(overrides: Partial<CompanyCardSummary> = {}): CompanyCardSummary {
  return {
    companyId: "company-1",
    ticker: "ACT",
    name: "Acme Corp",
    sector: null,
    firstReportPeriodEnd: "2016-06-30",
    latestReportPeriodEnd: "2024-06-30",
    reportCount: 9,
    comparisonCount: 8,
    isHistoricalPeak: false,
    latestComparison: null,
    ...overrides,
  };
}

function makeFakeRepository(overrides: Partial<CompanyRepository> = {}): CompanyRepository {
  return {
    listCompanies: async () => [] as Company[],
    getCompanyCardSummaries: async () => [makeCard()],
    getLatestComparisonSummaries: async () => [] as DiscoveryItemSummary[],
    getApplicationDataSummary: async () => makeSummary(),
    getCompanyByTicker: async () => null as CompanyDetail | null,
    getCompanyHistory: async () => null as CompanyHistory | null,
    ...overrides,
  };
}

describe("getCompaniesPageViewModel", () => {
  it("assembles summary, companies, and signal sections from the repository", async () => {
    const repository = makeFakeRepository();
    const viewModel = await getCompaniesPageViewModel(repository);
    expect(viewModel.companies).toHaveLength(1);
    expect(viewModel.summary.companyCount).toBe(1);
    expect(viewModel.latestSignalSections).toEqual([]);
  });

  it("selects the latest comparison via the repository's card summary, not re-derived", async () => {
    const comparison: CompanyCardSummary["latestComparison"] = {
      id: "cmp-1",
      companyId: "company-1",
      earlierPeriodEnd: "2023-06-30",
      laterPeriodEnd: "2024-06-30",
      gapMonths: 12,
      isTransition: false,
      isIrregularGap: false,
      isLatestForCompany: true,
      isHistoricalPeakChange: false,
      disclosureChangeScore: 0.5,
      disclosureChangeLabel: "Notable change",
      disclosureChangePercentile: 80,
      disclosureChangeQuality: "NEEDS_REVIEW",
      disclosureChangeQualityLabel: "Review recommended",
      disclosureChangePrimaryEligible: false,
      disclosureChangeWarning: "exclusion: feature quality is NEEDS_REVIEW",
      netToneChange: null,
      netToneChangeLabel: null,
      uncertaintyChange: null,
      uncertaintyChangeLabel: null,
      riskIntroductionRate: null,
      riskIntroductionLabel: null,
      riskRemovalRate: null,
      riskRemovalLabel: null,
      governanceChange: null,
      governanceChangeLabel: null,
      financialConditionChange: null,
      financialConditionChangeLabel: null,
      reportSideQuality: "GOOD",
      reportSideQualityLabel: "Analysis ready",
      reportSidePrimaryEligible: true,
      alignmentChangeQuality: "USABLE",
      alignmentChangeQualityLabel: "Usable attribution",
      alignmentChangePrimaryEligible: true,
      primaryFindingKey: null,
      secondaryFindingKey: null,
      tertiaryFindingKey: null,
      findingPayload: null,
    };
    const repository = makeFakeRepository({
      getCompanyCardSummaries: async () => [makeCard({ latestComparison: comparison })],
    });
    const viewModel = await getCompaniesPageViewModel(repository);
    expect(viewModel.companies[0].latestComparison?.id).toBe("cmp-1");
    expect(viewModel.companies[0].latestComparison?.disclosureChangePrimaryEligible).toBe(false);
  });
});

describe("buildLatestSignalSections", () => {
  it("groups items by discovery type into titled sections", () => {
    const items: DiscoveryItemSummary[] = [
      {
        id: "d1",
        companyId: "c1",
        companyTicker: "ACT",
        companyName: "Acme Corp",
        reportComparisonId: "cmp-1",
        discoveryType: "largest_uncertainty_increase",
        rank: 1,
        percentile: 90,
        supportingValue: 1.5,
        supportingUnit: "rate_per_1000_words",
        qualityLabel: "Analysis ready",
      },
    ];
    const sections = buildLatestSignalSections(items);
    expect(sections).toHaveLength(1);
    expect(sections[0].discoveryType).toBe("largest_uncertainty_increase");
    expect(sections[0].items).toHaveLength(1);
  });

  it("omits a section entirely when it has no qualifying items -- never renders an empty ranking", () => {
    const sections = buildLatestSignalSections([]);
    expect(sections).toEqual([]);
  });

  it("never produces a section for a feature-quality-gated discovery type", () => {
    const items: DiscoveryItemSummary[] = [
      {
        id: "d1",
        companyId: "c1",
        companyTicker: "ACT",
        companyName: "Acme Corp",
        reportComparisonId: "cmp-1",
        // Even if such an item somehow existed in the data, the section
        // title map only covers language-based types -- this type is not
        // among LANGUAGE_DISCOVERY_TYPES and must never surface as a titled
        // section.
        discoveryType: "largest_overall_change",
        rank: 1,
        percentile: 99,
        supportingValue: 0.9,
        supportingUnit: "score_0_1",
        qualityLabel: "Analysis ready",
      },
    ];
    const sections = buildLatestSignalSections(items);
    expect(sections.find((s) => s.discoveryType === "largest_overall_change")).toBeUndefined();
  });
});
