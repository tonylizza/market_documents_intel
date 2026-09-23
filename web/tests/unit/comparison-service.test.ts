import { describe, expect, it } from "vitest";
import { buildGovernanceSubcategoryMovers, buildTechnicalDetails, getComparisonPageViewModel } from "@/lib/services/comparison-service";
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
    getNarrativeUnitComparisons: async () => [],
    getStructuredTableComparisons: async () => [],
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
        earlierCount: null,
        laterCount: null,
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
        earlierCount: null,
        laterCount: null,
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

  it("separates financial_condition subcategory movers (Track 7F.4 item 12) from reportSideLanguageMetrics", async () => {
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
        earlierCount: null,
        laterCount: null,
        quality: "GOOD",
        primaryEligible: true,
      },
      {
        id: "m2",
        scope: "report_side",
        population: "financial_condition_subcategory",
        category: "financial_condition",
        subcategory: "revenue",
        earlierRatePer1000: null,
        laterRatePer1000: null,
        rateChange: null,
        absoluteRateChange: null,
        introducedRatePer1000: null,
        removedRatePer1000: null,
        retainedCount: null,
        earlierCount: 4,
        laterCount: 9,
        quality: "GOOD",
        primaryEligible: true,
      },
    ];
    const repository = makeFakeRepository({ getComparisonLanguageMetrics: async () => metrics });
    const viewModel = await getComparisonPageViewModel(repository, "cmp-1");
    expect(viewModel?.reportSideLanguageMetrics).toHaveLength(1);
    expect(viewModel?.reportSideLanguageMetrics[0].category).toBe("positive");
    expect(viewModel?.financialConditionSubcategoryMovers).toHaveLength(1);
    expect(viewModel?.financialConditionSubcategoryMovers[0].subcategory).toBe("revenue");
  });

  it("Track 7F.7a.1: separates governance subcategory movers from reportSideLanguageMetrics and computes governance-share contributions", async () => {
    function govRow(subcategory: string, earlierCount: number, laterCount: number): LanguageMetric {
      return {
        id: `gov-${subcategory}`,
        scope: "report_side",
        population: "governance_subcategory",
        category: "governance",
        subcategory,
        earlierRatePer1000: null,
        laterRatePer1000: null,
        rateChange: null,
        absoluteRateChange: null,
        introducedRatePer1000: null,
        removedRatePer1000: null,
        retainedCount: null,
        earlierCount,
        laterCount,
        quality: "GOOD",
        primaryEligible: true,
      };
    }
    const metrics: LanguageMetric[] = [
      govRow("board", 10, 20), // change 10
      govRow("audit", 5, 5), // change 0
      govRow("remuneration", 1, 9), // change 8
      govRow("litigation", 1, 2), // change 1, low-volume subcategory
    ];
    const repository = makeFakeRepository({ getComparisonLanguageMetrics: async () => metrics });
    const viewModel = await getComparisonPageViewModel(repository, "cmp-1");
    expect(viewModel?.reportSideLanguageMetrics).toHaveLength(0);
    // Top 3 by |change|: board (10), remuneration (8), litigation (1) -- audit (0) excluded.
    const movers = viewModel?.governanceSubcategoryMovers ?? [];
    expect(movers).toHaveLength(3);
    expect(movers.map((m) => m.subcategory)).toEqual(["board", "remuneration", "litigation"]);
    // Earlier total across all 4 rows = 10+5+1+1 = 17; board earlier share = 10/17.
    const board = movers.find((m) => m.subcategory === "board")!;
    expect(board.earlierShareContribution).toBeCloseTo(10 / 17, 6);
    // Later total = 20+5+9+2 = 36; board later share = 20/36.
    expect(board.laterShareContribution).toBeCloseTo(20 / 36, 6);
    expect(board.lowVolume).toBe(false);
    const litigation = movers.find((m) => m.subcategory === "litigation")!;
    expect(litigation.lowVolume).toBe(true);
  });
});

describe("buildGovernanceSubcategoryMovers", () => {
  it("returns an empty list when there are no governance_subcategory rows", () => {
    expect(buildGovernanceSubcategoryMovers([])).toEqual([]);
  });
});
