import { describe, expect, it } from "vitest";
import { getComparisonEvidencePage, getComparisonEvidenceSummary } from "@/lib/services/comparison-evidence-service";
import { parseComparisonEvidenceFilters } from "@/lib/services/comparison-evidence-params";
import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type { PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import type { ComparisonEvidenceItem } from "@/lib/domain/passage";

function makeDetail(overrides: Partial<ReportComparisonDetail> = {}): ReportComparisonDetail {
  return {
    id: "cmp-1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    gapMonths: 12,
    isTransition: false,
    isIrregularGap: false,
    isLatestForCompany: true,
    isHistoricalPeakChange: false,
    disclosureChangeScore: null,
    disclosureChangeLabel: null,
    disclosureChangePercentile: null,
    disclosureChangeQuality: null,
    disclosureChangeQualityLabel: null,
    disclosureChangePrimaryEligible: null,
    disclosureChangeWarning: null,
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
    dictionaryMatchRateEarlier: 0.9,
    dictionaryMatchRateLater: 0.9,
    ambiguousWordShare: 0.01,
    collisionFlaggedWordShare: 0.01,
    unmatchedWordShare: 0.01,
    structuredContentExclusionShare: 0.01,
    reportSideWarning: null,
    alignmentChangeWarning: null,
    ...overrides,
  };
}

function makeComposition(): PassageComposition {
  return {
    comparisonId: "cmp-1",
    totalCount: 6,
    buckets: [
      { status: "NEW", count: 1, share: 1 / 6 },
      { status: "REMOVED", count: 1, share: 1 / 6 },
      { status: "SUBSTANTIALLY_MODIFIED", count: 1, share: 1 / 6 },
      { status: "LIGHTLY_MODIFIED", count: 1, share: 1 / 6 },
      { status: "UNCHANGED", count: 1, share: 1 / 6 },
      { status: "AMBIGUOUS", count: 1, share: 1 / 6 },
    ],
    qualityNote: "note",
  };
}

function makeFakeRepository(overrides: Partial<ComparisonRepository> = {}): ComparisonRepository {
  return {
    getComparisonById: async () => makeDetail(),
    getComparisonLanguageMetrics: async () => [],
    getComparisonPassageComposition: async () => makeComposition(),
    getComparisonEvidence: async () => [],
    countComparisonEvidence: async () => 0,
    getComparisonEvidenceFilterOptions: async () => ({ confidenceLevels: [], categories: [], subcategoriesByCategory: {} }),
    ...overrides,
  };
}

describe("getComparisonEvidenceSummary", () => {
  it("returns null for an unknown comparison id (drives notFound())", async () => {
    const repository = makeFakeRepository({ getComparisonById: async () => null });
    expect(await getComparisonEvidenceSummary(repository, "missing")).toBeNull();
  });

  it("combines header + composition counts without a new query beyond the two existing ones", async () => {
    const repository = makeFakeRepository();
    const summary = await getComparisonEvidenceSummary(repository, "cmp-1");
    expect(summary?.totalCount).toBe(6);
    expect(summary?.counts.NEW).toBe(1);
    expect(summary?.counts.UNCHANGED).toBe(1);
    expect(summary?.companyTicker).toBe("ACT");
  });

  it("fills in zero for any status with no rows (never undefined)", async () => {
    const repository = makeFakeRepository({
      getComparisonPassageComposition: async () => ({ comparisonId: "cmp-1", totalCount: 0, buckets: [], qualityNote: "" }),
    });
    const summary = await getComparisonEvidenceSummary(repository, "cmp-1");
    expect(summary?.counts.NEW).toBe(0);
    expect(summary?.counts.AMBIGUOUS).toBe(0);
  });
});

describe("getComparisonEvidencePage", () => {
  it("builds pagination from the count query, independent of the page's own row count", async () => {
    const item: ComparisonEvidenceItem = {
      passageComparisonId: "pc1",
      alignmentStatus: "NEW",
      alignmentType: "UNMATCHED_LATER",
      confidence: "HIGH",
      confidenceLabel: "High confidence",
      collisionFlag: false,
      splitMergeFlag: false,
      contentScore: null,
      earlier: null,
      later: { passageId: "p1", heading: "New disclosure", excerpt: [{ text: "text", matched: false }], firstPageNumber: 1, lastPageNumber: 1, wordCount: 2 },
    };
    const repository = makeFakeRepository({
      getComparisonEvidence: async () => [item],
      countComparisonEvidence: async () => 42,
    });
    const page = await getComparisonEvidencePage(repository, "cmp-1", parseComparisonEvidenceFilters({}));
    expect(page.items).toHaveLength(1);
    expect(page.pagination.totalCount).toBe(42);
    expect(page.pagination.totalPages).toBeGreaterThan(1);
  });
});
