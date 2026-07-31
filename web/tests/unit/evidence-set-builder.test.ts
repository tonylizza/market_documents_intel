import { describe, expect, it } from "vitest";
import { buildEvidenceSet } from "@/lib/services/qa/evidence-set-builder";
import { getQaConfig, type QaConfig } from "@/lib/config/qa-config";
import type { QueryAnalysis, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";
import type { RetrievalContext } from "@/lib/domain/retrieval";

function context(overrides: Partial<RetrievalContext> = {}): RetrievalContext {
  return {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED",
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "ACT",
    companyName: "AfroCentric Investment Corporation Limited",
    reportSide: "LATER",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    reportPeriodEnd: "2024-12-31",
    earlierPeriodEnd: "2023-12-31",
    laterPeriodEnd: "2024-12-31",
    heading: "Liquidity risk",
    passageType: "PARAGRAPH",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    reportSideQuality: "GOOD",
    alignmentChangeQuality: "GOOD",
    collisionFlag: false,
    splitMergeFlag: false,
    irregularGapFlag: false,
    firstPageNumber: 10,
    lastPageNumber: 10,
    wordCount: 40,
    text: "The group maintains adequate liquidity headroom and there is no material uncertainty.",
    categories: ["financial_condition"],
    riskSubcategories: [],
    ...overrides,
  };
}

function candidate(overrides: Partial<RerankedEvidenceCandidate> = {}, contextOverrides: Partial<RetrievalContext> = {}): RerankedEvidenceCandidate {
  const ctx = context(contextOverrides);
  return {
    candidateId: ctx.contextId,
    passageId: ctx.passageId,
    retrievalContextId: ctx.contextId,
    context: ctx,
    citation: {
      publicationId: "pub-1",
      retrievalContextId: ctx.contextId,
      passageId: ctx.passageId,
      passageComparisonId: ctx.passageComparisonId,
      reportComparisonId: ctx.reportComparisonId,
      reportSide: ctx.reportSide,
      reportId: ctx.reportId,
      firstPageNumber: ctx.firstPageNumber,
      lastPageNumber: ctx.lastPageNumber,
      label: "ACT, p. 10",
    },
    sources: ["keyword"],
    lexicalRankPosition: 1,
    semanticRawRank: null,
    semanticAdjustedRank: null,
    semanticRawSimilarity: null,
    semanticAdjustedScore: null,
    qualityFactor: null,
    qualityExplanationCode: null,
    rrfRank: 1,
    relevanceScore: 0.8,
    relevanceRank: 1,
    rerankerMethod: "baseline",
    numericFragmentSeverity: null,
    conceptCoverageScore: 1,
    directResponsivenessScore: 1,
    directResponsivenessRank: 1,
    evidenceEligible: true,
    ineligibilityReasons: [],
    ...overrides,
  };
}

function analysis(overrides: Partial<QueryAnalysis> = {}): QueryAnalysis {
  return {
    question: "What is ACT's liquidity risk?",
    normalizedQuestion: "What is ACT's liquidity risk?",
    tickers: ["ACT"],
    dateRange: null,
    comparisonDirection: null,
    directionConfidence: null,
    alignmentStatuses: [],
    requestedReportSides: [],
    categories: [],
    subcategories: [],
    questionType: "descriptive",
    requestedScope: "single_company",
    requiredTicker: "ACT",
    requiredReportSide: null,
    requiredCategory: null,
    unresolvedTerms: [],
    warnings: [],
    materialElements: [],
    requiredConceptFamilies: [],
    optionalConceptFamilies: [],
    directionalConcepts: [],
    quantitativeConcepts: [],
    causalConcepts: [],
    ambiguitySensitiveConcepts: [],
    unresolvedRequiredConcepts: [],
    ...overrides,
  };
}

const config: QaConfig = { ...getQaConfig(), maxEvidenceSetSize: 5 };

describe("buildEvidenceSet -- deduplication", () => {
  it("rejects a second candidate for the same passage id as a duplicate", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "passage-1" }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "passage-1" }),
    ];
    const result = buildEvidenceSet(candidates, analysis(), config);
    expect(result.selected).toHaveLength(1);
    expect(result.selected[0].candidateId).toBe("a");
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "b", reason: "DUPLICATE" }));
  });

  it("rejects a near-duplicate by normalized text even across different passage ids", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "passage-1", text: "Liquidity risk is well managed." }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "passage-2", text: "  liquidity   risk is well   managed.  " }),
    ];
    const result = buildEvidenceSet(candidates, analysis(), config);
    expect(result.selected).toHaveLength(1);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "b", reason: "DUPLICATE" }));
  });
});

describe("buildEvidenceSet -- relevance floor", () => {
  it("rejects a semantic-only candidate below the corpus weak-match floor", () => {
    const candidates = [
      candidate(
        { candidateId: "weak", relevanceRank: 1, sources: ["semantic"], semanticRawSimilarity: 0.5, lexicalRankPosition: null },
        { contextId: "weak" },
      ),
    ];
    const result = buildEvidenceSet(candidates, analysis(), config);
    expect(result.selected).toHaveLength(0);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "weak", reason: "BELOW_RELEVANCE_FLOOR" }));
  });

  it("does not apply the semantic relevance floor to a keyword-sourced candidate", () => {
    const candidates = [candidate({ candidateId: "kw", relevanceRank: 1, sources: ["keyword"] }, { contextId: "kw" })];
    const result = buildEvidenceSet(candidates, analysis(), config);
    expect(result.selected).toHaveLength(1);
  });

  it("keeps a semantic candidate whose similarity is at or above the floor", () => {
    const candidates = [
      candidate(
        { candidateId: "strong", relevanceRank: 1, sources: ["semantic"], semanticRawSimilarity: 0.9, lexicalRankPosition: null },
        { contextId: "strong" },
      ),
    ];
    const result = buildEvidenceSet(candidates, analysis(), config);
    expect(result.selected).toHaveLength(1);
  });
});

describe("buildEvidenceSet -- scope compliance", () => {
  it("rejects a candidate whose company doesn't match the required ticker", () => {
    const candidates = [candidate({ candidateId: "wrong-company", relevanceRank: 1 }, { contextId: "wrong-company", companyTicker: "BEL" })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: "ACT" }), config);
    expect(result.selected).toHaveLength(0);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "wrong-company", reason: "OUT_OF_SCOPE" }));
  });

  it("rejects a candidate whose report side doesn't match the required side", () => {
    const candidates = [candidate({ candidateId: "wrong-side", relevanceRank: 1 }, { contextId: "wrong-side", reportSide: "EARLIER" })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null, requiredReportSide: "LATER" }), config);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "wrong-side", reason: "OUT_OF_SCOPE" }));
  });

  it("rejects a candidate with an unverifiable (null) report side when a side is required", () => {
    const candidates = [candidate({ candidateId: "null-side", relevanceRank: 1 }, { contextId: "null-side", reportSide: null })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null, requiredReportSide: "LATER" }), config);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "null-side", reason: "OUT_OF_SCOPE" }));
  });

  it("rejects a candidate missing the required category", () => {
    const candidates = [candidate({ candidateId: "wrong-category", relevanceRank: 1 }, { contextId: "wrong-category", categories: ["governance"] })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null, requiredCategory: "financial_condition" }), config);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "wrong-category", reason: "OUT_OF_SCOPE" }));
  });

  it("keeps a candidate that satisfies every required scope constraint", () => {
    const candidates = [candidate({ candidateId: "ok", relevanceRank: 1 }, { contextId: "ok", companyTicker: "ACT", reportSide: "LATER", categories: ["financial_condition"] })];
    const result = buildEvidenceSet(
      candidates,
      analysis({ requiredTicker: "ACT", requiredReportSide: "LATER", requiredCategory: "financial_condition" }),
      config,
    );
    expect(result.selected).toHaveLength(1);
  });
});

describe("buildEvidenceSet -- greedy coverage selection", () => {
  it("always considers at least two candidates even when the second adds no new facet coverage", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "p-a", text: "First liquidity risk passage.", categories: ["financial_condition"] }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "p-b", text: "Second liquidity risk passage.", categories: ["financial_condition"] }),
    ];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(result.selected.map((s) => s.candidateId)).toEqual(["a", "b"]);
  });

  it("rejects a third candidate that adds no new facet coverage as redundant", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "p-a", text: "First liquidity risk passage.", categories: ["financial_condition"] }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "p-b", text: "Second liquidity risk passage.", categories: ["financial_condition"] }),
      candidate({ candidateId: "c", relevanceRank: 3 }, { contextId: "c", passageId: "p-c", text: "Third liquidity risk passage.", categories: ["financial_condition"] }),
    ];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(result.selected).toHaveLength(2);
    expect(result.rejected).toContainEqual(expect.objectContaining({ candidateId: "c", reason: "REDUNDANT_NO_NEW_COVERAGE" }));
  });

  it("accepts a third candidate that covers a genuinely new facet", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "p-a", text: "First liquidity risk passage.", categories: ["financial_condition"] }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "p-b", text: "Second liquidity risk passage.", categories: ["financial_condition"] }),
      candidate({ candidateId: "c", relevanceRank: 3 }, { contextId: "c", passageId: "p-c", text: "A governance passage entirely.", categories: ["governance"] }),
    ];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(result.selected.map((s) => s.candidateId)).toContain("c");
  });

  it("never selects more than maxEvidenceSetSize items", () => {
    const realCategories = ["risk", "financial_condition", "governance", "strategy"];
    const candidates = Array.from({ length: 10 }, (_, i) =>
      candidate(
        { candidateId: `c${i}`, relevanceRank: i + 1 },
        {
          contextId: `c${i}`,
          passageId: `p${i}`,
          text: `Distinct passage number ${i} about a topic.`,
          categories: [realCategories[i % realCategories.length]],
          riskSubcategories: [`subcat${i}`],
        },
      ),
    );
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), { ...config, maxEvidenceSetSize: 3 });
    expect(result.selected).toHaveLength(3);
  });

  it("preserves full citation identity on every selected item, unchanged from the input candidate", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a" })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(result.selected[0].citation).toEqual(candidates[0].citation);
  });
});

describe("buildEvidenceSet -- coverage computation", () => {
  it("computes coverageRatio as the fraction of required facets actually covered", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", categories: ["financial_condition"] })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null, requiredCategory: "financial_condition" }), config);
    expect(result.coverage.coverageRatio).toBe(1);
  });

  it("returns a coverageRatio below 1 when a required facet is never covered", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", categories: ["governance"] })];
    const result = buildEvidenceSet(
      candidates,
      analysis({ requiredTicker: null, alignmentStatuses: ["NEW"], requiredCategory: "governance" }),
      config,
    );
    expect(result.coverage.coverageRatio).toBeLessThan(1);
  });

  it("defaults coverageRatio to 1 when the question has no hard facet requirements", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a" })];
    const result = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(result.coverage.coverageRatio).toBe(1);
  });
});

describe("buildEvidenceSet -- Milestone 7B.1c Phase 5 narrow/broad direct-responsiveness gate", () => {
  it("rejects an in-scope but not directly-responsive candidate as NOT_DIRECTLY_RESPONSIVE for a narrow (single_company) question", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1, evidenceEligible: false }, { contextId: "a" })];
    const result = buildEvidenceSet(candidates, analysis({ requestedScope: "single_company" }), config);
    expect(result.selected).toHaveLength(0);
    expect(result.rejected).toEqual([{ candidateId: "a", passageId: "passage-1", retrievalContextId: "a", reason: "NOT_DIRECTLY_RESPONSIVE" }]);
  });

  it("selects an eligible, in-scope candidate for a narrow question", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1, evidenceEligible: true }, { contextId: "a" })];
    const result = buildEvidenceSet(candidates, analysis({ requestedScope: "single_company" }), config);
    expect(result.selected.map((s) => s.candidateId)).toEqual(["a"]);
  });

  it("does not apply the direct-responsiveness gate for a broad (corpus_wide) question", () => {
    const candidates = [candidate({ candidateId: "a", relevanceRank: 1, evidenceEligible: false }, { contextId: "a" })];
    const result = buildEvidenceSet(candidates, analysis({ requestedScope: "corpus_wide", requiredTicker: null }), config);
    expect(result.selected.map((s) => s.candidateId)).toEqual(["a"]);
    expect(result.rejected.some((r) => r.reason === "NOT_DIRECTLY_RESPONSIVE")).toBe(false);
  });
});

describe("buildEvidenceSet -- determinism", () => {
  it("produces identical output across repeated calls with the same input", () => {
    const candidates = [
      candidate({ candidateId: "a", relevanceRank: 1 }, { contextId: "a" }),
      candidate({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "passage-2" }),
    ];
    const first = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    const second = buildEvidenceSet(candidates, analysis({ requiredTicker: null }), config);
    expect(first.selected.map((s) => s.candidateId)).toEqual(second.selected.map((s) => s.candidateId));
  });
});
