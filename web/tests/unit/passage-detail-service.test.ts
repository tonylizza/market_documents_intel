import { describe, expect, it } from "vitest";
import { getPassageDetailViewModel } from "@/lib/services/passage-detail-service";
import type { PassageRepository } from "@/lib/repositories/passage-repository";
import type { PassageComparisonDetail, PassageSideDetail } from "@/lib/domain/passage";

function makeSide(overrides: Partial<PassageSideDetail> = {}): PassageSideDetail {
  return {
    passageId: "p1",
    heading: "Liquidity",
    text: "The group maintains adequate liquidity.",
    wordCount: 6,
    firstPageNumber: 10,
    lastPageNumber: 10,
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<PassageComparisonDetail> = {}): PassageComparisonDetail {
  return {
    passageComparisonId: "pc1",
    reportComparisonId: "rc1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    contentScore: 0.9,
    semanticSimilarity: 0.95,
    lexicalSimilarity: 0.9,
    headingSimilarity: 1,
    positionDifference: 0.01,
    collisionFlag: false,
    splitMergeFlag: false,
    reviewReason: null,
    earlier: makeSide(),
    later: makeSide({ passageId: "p2" }),
    ...overrides,
  };
}

function makeFakeRepository(detail: PassageComparisonDetail | null): PassageRepository {
  return {
    searchPassages: async () => [],
    countPassageSearchResults: async () => ({ count: 0, capped: false }),
    getPassageFilterOptions: async () => ({
      companies: [],
      alignmentStatuses: [],
      confidenceLevels: [],
      passageTypes: [],
      categories: [],
      subcategoriesByCategory: {},
      reportSideQualities: [],
      alignmentChangeQualities: [],
    }),
    getPassageComparisonById: async () => detail,
    getPassageLanguageSignals: async () => [],
  };
}

describe("getPassageDetailViewModel", () => {
  it("returns null for an unknown passage comparison id", async () => {
    const result = await getPassageDetailViewModel(makeFakeRepository(null), "missing");
    expect(result).toBeNull();
  });

  it("computes a diff for a two-sided (matched) passage", async () => {
    const result = await getPassageDetailViewModel(makeFakeRepository(makeDetail()), "pc1");
    expect(result?.diff).not.toBeNull();
    expect(result?.diff?.diffed).toBe(true);
  });

  it("returns a null diff for a NEW passage (no earlier side)", async () => {
    const detail = makeDetail({ alignmentStatus: "NEW", earlier: null });
    const result = await getPassageDetailViewModel(makeFakeRepository(detail), "pc1");
    expect(result?.diff).toBeNull();
    expect(result?.detail.earlier).toBeNull();
    expect(result?.detail.later).not.toBeNull();
  });

  it("returns a null diff for a REMOVED passage (no later side)", async () => {
    const detail = makeDetail({ alignmentStatus: "REMOVED", later: null });
    const result = await getPassageDetailViewModel(makeFakeRepository(detail), "pc1");
    expect(result?.diff).toBeNull();
    expect(result?.detail.later).toBeNull();
    expect(result?.detail.earlier).not.toBeNull();
  });

  it("returns a null diff for a one-sided AMBIGUOUS passage", async () => {
    const detail = makeDetail({ alignmentStatus: "AMBIGUOUS", later: null });
    const result = await getPassageDetailViewModel(makeFakeRepository(detail), "pc1");
    expect(result?.diff).toBeNull();
  });
});
