import { afterEach, describe, expect, it, vi } from "vitest";
import { getComparisonView } from "@/lib/services/comparison-facade";
import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type { LanguageMetric, PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import type { NarrativeUnitComparison, StructuredTableComparison } from "@/lib/domain/cutover-comparison";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

function makeDetail(overrides: Partial<ReportComparisonDetail> = {}): ReportComparisonDetail {
  return {
    ...makeComparisonSummary(),
    companyTicker: "BEL",
    companyName: "Bellwether Test Ltd",
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
    totalCount: 0,
    buckets: [],
    qualityNote: "note",
  };
}

function makeNarrative(overrides: Partial<NarrativeUnitComparison> = {}): NarrativeUnitComparison {
  return {
    comparisonBackend: "SEMANTIC_UNIT",
    status: "RESOLVED",
    schedule: "FINANCIAL_PERFORMANCE",
    unitKey: "gross_margin",
    alignmentStatus: "MATCHED",
    alignmentConfidence: "HIGH",
    analyticalMode: "LEXICAL_ONLY",
    lexicalMetrics: {
      tfidfCosine: 0.75,
      unigramJaccard: 0.48,
      bigramJaccard: 0.35,
      editSimilarity: 0.66,
      sequenceSimilarity: 0.65,
      wordCountChange: -17,
      wordCountChangePct: -0.27,
    },
    earlierWordCount: 64,
    laterWordCount: 47,
    earlierProvenance: null,
    laterProvenance: null,
    reviewReason: null,
    ...overrides,
  };
}

function makeStructured(overrides: Partial<StructuredTableComparison> = {}): StructuredTableComparison {
  return {
    comparisonBackend: "STRUCTURED_TABLE",
    status: "RESOLVED",
    tableFamilyKey: "total_remuneration_outcomes",
    rowAlignments: [],
    columnAlignments: [],
    valueChangeEvents: [],
    footnotes: [],
    earlierProvenance: null,
    laterProvenance: null,
    reviewReason: null,
    ...overrides,
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

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("getComparisonView", () => {
  it("flag off -> always LEGACY_PASSAGE, even for a comparison that has cutover rows", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "false");
    const repository = makeFakeRepository({
      getNarrativeUnitComparisons: async () => [makeNarrative()],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("LEGACY_PASSAGE");
  });

  it("flag on + no cutover row for this comparison -> LEGACY_PASSAGE (out of scope)", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository();

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("LEGACY_PASSAGE");
  });

  it("flag on + resolved narrative row -> CUTOVER with narrative populated", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({
      getNarrativeUnitComparisons: async () => [makeNarrative({ status: "RESOLVED" })],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("CUTOVER");
    if (view?.backend === "CUTOVER") {
      expect(view.narrative).toHaveLength(1);
      expect(view.narrative[0].status).toBe("RESOLVED");
      expect(view.structured).toEqual([]);
      // Legacy stays available as diagnostic context, never as the primary result.
      expect(view.legacy).toBeDefined();
    }
  });

  it("flag on + unresolved narrative row -> CUTOVER with unresolved status, never silently replaced by legacy", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({
      getNarrativeUnitComparisons: async () => [makeNarrative({ status: "UNRESOLVED_UPSTREAM", lexicalMetrics: null })],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("CUTOVER");
    if (view?.backend === "CUTOVER") {
      expect(view.narrative[0].status).toBe("UNRESOLVED_UPSTREAM");
    }
  });

  it("flag on + structured rows only -> CUTOVER with structured populated and narrative empty", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({
      getStructuredTableComparisons: async () => [
        makeStructured({ tableFamilyKey: "total_remuneration_outcomes", status: "RESOLVED" }),
        makeStructured({ tableFamilyKey: "ned_remuneration_policy_table", status: "UNRESOLVED_UPSTREAM" }),
      ],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("CUTOVER");
    if (view?.backend === "CUTOVER") {
      expect(view.narrative).toEqual([]);
      expect(view.structured).toHaveLength(2);
    }
  });

  it("flag on + both narrative and structured rows -> CUTOVER carries both simultaneously (ACT's real shape)", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({
      getNarrativeUnitComparisons: async () => [makeNarrative({ unitKey: "cfo_conclusion" })],
      getStructuredTableComparisons: async () => [makeStructured()],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("CUTOVER");
    if (view?.backend === "CUTOVER") {
      expect(view.narrative[0].unitKey).toBe("cfo_conclusion");
      expect(view.structured).toHaveLength(1);
    }
  });

  it("flag on + two narrative rows (7D.2c: cfo_conclusion + healthcare_services_review) -> CUTOVER carries both, neither silently dropped", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({
      getNarrativeUnitComparisons: async () => [
        makeNarrative({ unitKey: "cfo_conclusion", status: "UNRESOLVED_UPSTREAM", lexicalMetrics: null }),
        makeNarrative({ unitKey: "healthcare_services_review", status: "RESOLVED" }),
      ],
    });

    const view = await getComparisonView(repository, "cmp-1");
    expect(view?.backend).toBe("CUTOVER");
    if (view?.backend === "CUTOVER") {
      expect(view.narrative).toHaveLength(2);
      const byUnitKey = new Map(view.narrative.map((n) => [n.unitKey, n]));
      expect(byUnitKey.get("cfo_conclusion")?.status).toBe("UNRESOLVED_UPSTREAM");
      expect(byUnitKey.get("healthcare_services_review")?.status).toBe("RESOLVED");
    }
  });

  it("unknown comparison id -> null regardless of flag", async () => {
    vi.stubEnv("SEMANTIC_COMPARISON_CUTOVER_ENABLED", "true");
    const repository = makeFakeRepository({ getComparisonById: async () => null });

    const view = await getComparisonView(repository, "does-not-exist");
    expect(view).toBeNull();
  });
});
