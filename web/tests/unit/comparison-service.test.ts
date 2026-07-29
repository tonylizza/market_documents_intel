import { describe, expect, it } from "vitest";
import { buildTechnicalDetails, getComparisonPageViewModel } from "@/lib/services/comparison-service";
import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type { LanguageMetric, PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

function makeDetail(overrides: Partial<ReportComparisonDetail> = {}): ReportComparisonDetail {
  return {
    ...makeComparisonSummary(),
    companyTicker: "ACT",
    companyName: "Acme Corp",
    dictionaryMatchRateEarlier: 0.9,
    dictionaryMatchRateLater: 0.91,
    ambiguousWordShare: 0.02,
    collisionFlaggedWordShare: 0.01,
    unmatchedWordShare: 0.05,
    structuredContentExclusionShare: 0.1,
    reportSideWarning: null,
    alignmentChangeWarning: null,
    ...overrides,
  };
}

function makeComposition(): PassageComposition {
  return {
    comparisonId: "cmp-1",
    totalCount: 10,
    buckets: [
      { status: "NEW", count: 3, share: 0.3 },
      { status: "REMOVED", count: 2, share: 0.2 },
      { status: "SUBSTANTIALLY_MODIFIED", count: 1, share: 0.1 },
      { status: "LIGHTLY_MODIFIED", count: 1, share: 0.1 },
      { status: "UNCHANGED", count: 2, share: 0.2 },
      { status: "AMBIGUOUS", count: 1, share: 0.1 },
    ],
    qualityNote: "note",
  };
}

function makeFakeRepository(overrides: Partial<ComparisonRepository> = {}): ComparisonRepository {
  return {
    getComparisonById: async () => makeDetail(),
    getComparisonLanguageMetrics: async () => [] as LanguageMetric[],
    getComparisonPassageComposition: async () => makeComposition(),
    getComparisonEvidence: async () => [],
    countComparisonEvidence: async () => 0,
    getComparisonEvidenceFilterOptions: async () => ({ confidenceLevels: [], categories: [], subcategoriesByCategory: {} }),
    ...overrides,
  };
}

describe("buildTechnicalDetails", () => {
  it("maps every technical field straight from the comparison row, never recomputing", () => {
    const detail = makeDetail({ ambiguousWordShare: 0.42, reportSideWarning: "some warning" });
    const technical = buildTechnicalDetails(detail);
    expect(technical.ambiguousWordShare).toBe(0.42);
    expect(technical.reportSideWarning).toBe("some warning");
  });
});

describe("getComparisonPageViewModel", () => {
  it("returns null when the comparison doesn't exist -- page renders 404", async () => {
    const repository = makeFakeRepository({ getComparisonById: async () => null });
    const viewModel = await getComparisonPageViewModel(repository, "missing-id");
    expect(viewModel).toBeNull();
  });

  it("assembles findings, headline metrics, technical details, and passage composition from one comparison fetch", async () => {
    const repository = makeFakeRepository();
    const viewModel = await getComparisonPageViewModel(repository, "cmp-1");
    expect(viewModel).not.toBeNull();
    expect(viewModel?.headlineMetrics).toHaveLength(6);
    expect(viewModel?.passageComposition.totalCount).toBe(10);
  });

  it("splits language metrics into report-side vs. alignment-change (excl.-ambiguous) sections", async () => {
    const metrics: LanguageMetric[] = [
      {
        id: "m1",
        scope: "report_side",
        population: "primary_narrative",
        category: "positive",
        subcategory: null,
        earlierRatePer1000: 1,
        laterRatePer1000: 2,
        rateChange: 1,
        absoluteRateChange: 1,
        introducedRatePer1000: null,
        removedRatePer1000: null,
        retainedCount: null,
        quality: "GOOD",
        primaryEligible: true,
      },
      {
        id: "m2",
        scope: "alignment_change",
        population: "primary_narrative_excl_ambiguous",
        category: "risk",
        subcategory: null,
        earlierRatePer1000: null,
        laterRatePer1000: null,
        rateChange: null,
        absoluteRateChange: null,
        introducedRatePer1000: 3,
        removedRatePer1000: 1,
        retainedCount: 5,
        quality: "USABLE",
        primaryEligible: true,
      },
    ];
    const repository = makeFakeRepository({ getComparisonLanguageMetrics: async () => metrics });
    const viewModel = await getComparisonPageViewModel(repository, "cmp-1");
    expect(viewModel?.reportSideLanguageMetrics).toHaveLength(1);
    expect(viewModel?.reportSideLanguageMetrics[0].category).toBe("positive");
    expect(viewModel?.alignmentChangeLanguageMetrics).toHaveLength(1);
    expect(viewModel?.alignmentChangeLanguageMetrics[0].category).toBe("risk");
  });
});
