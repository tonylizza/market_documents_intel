import { describe, expect, it } from "vitest";
import { BaselineQaReranker, ConceptCoverageQaReranker, createQaReranker, QualityAwareQaReranker } from "@/lib/services/qa/qa-reranker";
import type { EvidenceCandidate, QueryAnalysis } from "@/lib/domain/qa-evidence";
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
    text: "The group maintains adequate liquidity headroom and there is no material uncertainty about its ability to meet obligations.",
    categories: [],
    riskSubcategories: [],
    ...overrides,
  };
}

function candidate(overrides: Partial<EvidenceCandidate> = {}, contextOverrides: Partial<RetrievalContext> = {}): EvidenceCandidate {
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
    ...overrides,
  };
}

const noAnalysis = {} as QueryAnalysis;

describe("BaselineQaReranker", () => {
  it("ranks a better-fused (lower rrfRank number) candidate above a worse one", () => {
    const candidates = [
      candidate({ candidateId: "a", rrfRank: 5 }, { contextId: "a" }),
      candidate({ candidateId: "b", rrfRank: 1 }, { contextId: "b" }),
    ];
    const reranked = new BaselineQaReranker().rerank("liquidity risk", candidates, noAnalysis);
    expect(reranked[0].candidateId).toBe("b");
    expect(reranked[0].relevanceRank).toBe(1);
    expect(reranked[1].relevanceRank).toBe(2);
  });

  it("never computes a numeric-fragment severity (baseline doesn't evaluate quality features)", () => {
    const reranked = new BaselineQaReranker().rerank("liquidity risk", [candidate()], noAnalysis);
    expect(reranked[0].numericFragmentSeverity).toBeNull();
  });
});

describe("ConceptCoverageQaReranker", () => {
  it("ranks a candidate matching more question terms above one matching fewer", () => {
    const candidates = [
      candidate({ candidateId: "low" }, { contextId: "low", heading: "Unrelated", text: "Something about governance structure." }),
      candidate({ candidateId: "high" }, { contextId: "high", heading: "Liquidity risk", text: "The group discusses liquidity risk exposure." }),
    ];
    const reranked = new ConceptCoverageQaReranker().rerank("What is the company's liquidity risk exposure?", candidates, noAnalysis);
    expect(reranked[0].candidateId).toBe("high");
  });

  it("scores zero when no question terms appear in the passage", () => {
    const reranked = new ConceptCoverageQaReranker().rerank(
      "What is disclosed about foreign exchange?",
      [candidate({}, { heading: "Board composition", text: "The board has five members." })],
      noAnalysis,
    );
    expect(reranked[0].relevanceScore).toBe(0);
  });
});

describe("QualityAwareQaReranker", () => {
  it("demotes a heading-only fragment relative to a substantive passage with equal concept coverage", () => {
    const candidates = [
      candidate({ candidateId: "fragment" }, { contextId: "fragment", heading: "Liquidity risk", text: "Liquidity risk", wordCount: 2 }),
      candidate(
        { candidateId: "substantive" },
        {
          contextId: "substantive",
          heading: "Liquidity risk",
          text: "The group's liquidity risk exposure is managed through a mix of committed facilities and cash reserves, reviewed quarterly by the board.",
          wordCount: 20,
        },
      ),
    ];
    const reranked = new QualityAwareQaReranker().rerank("What is the company's liquidity risk?", candidates, noAnalysis);
    expect(reranked[0].candidateId).toBe("substantive");
  });

  it("does not penalize a short passage that carries a real financial-language signal", () => {
    const reranked = new QualityAwareQaReranker().rerank(
      "What is the company's liquidity risk?",
      [candidate({}, { heading: "Liquidity risk", text: "Liquidity risk", wordCount: 2, categories: ["financial_condition"] })],
      noAnalysis,
    );
    expect(reranked[0].relevanceScore).toBeGreaterThan(0);
  });

  it("reuses an already-computed quality factor from candidate generation instead of recomputing", () => {
    const reranked = new QualityAwareQaReranker().rerank(
      "liquidity risk",
      [candidate({ qualityFactor: 0.5 }, { heading: "Liquidity risk", text: "Liquidity risk", wordCount: 2 })],
      noAnalysis,
    );
    // relevanceScore = coverage * qualityFactor; question terms fully match
    // (coverage = 1), so qualityFactor of exactly 0.5 (an unusual,
    // clearly-not-default value) proves the precomputed factor was reused
    // rather than freshly derived.
    expect(reranked[0].relevanceScore).toBeCloseTo(1 * 0.5, 5);
  });

  it("classifies a bare numeric fragment as fragment_without_context when no nearby candidate exists", () => {
    const reranked = new QualityAwareQaReranker().rerank(
      "What is the operating margin?",
      [candidate({}, { heading: "Operating margin", text: "Operating margin (0.9%) (0.2%) (13.9%)", wordCount: 5, firstPageNumber: 50 })],
      noAnalysis,
    );
    expect(reranked[0].numericFragmentSeverity).toBe("fragment_without_context");
  });

  it("classifies a bare numeric fragment as fragment_with_context when another candidate shares an adjacent page", () => {
    const candidates = [
      candidate(
        { candidateId: "numeric" },
        { contextId: "numeric", heading: "Operating margin", text: "Operating margin (0.9%) (0.2%) (13.9%)", wordCount: 5, firstPageNumber: 50 },
      ),
      candidate(
        { candidateId: "explanatory" },
        { contextId: "explanatory", heading: "Margin discussion", text: "Operating margin declined due to input cost pressure.", wordCount: 9, firstPageNumber: 50 },
      ),
    ];
    const reranked = new QualityAwareQaReranker().rerank("What is the operating margin?", candidates, noAnalysis);
    const numeric = reranked.find((c) => c.candidateId === "numeric")!;
    expect(numeric.numericFragmentSeverity).toBe("fragment_with_context");
  });
});

describe("createQaReranker factory", () => {
  it("constructs the reranker matching the requested method", () => {
    expect(createQaReranker("baseline")).toBeInstanceOf(BaselineQaReranker);
    expect(createQaReranker("concept_coverage")).toBeInstanceOf(ConceptCoverageQaReranker);
    expect(createQaReranker("quality_aware")).toBeInstanceOf(QualityAwareQaReranker);
  });
});

describe("determinism and rank contiguity across all strategies", () => {
  it.each([new BaselineQaReranker(), new ConceptCoverageQaReranker(), new QualityAwareQaReranker()])(
    "produces identical output across repeated calls and contiguous 1-based ranks",
    (reranker) => {
      const candidates = [
        candidate({ candidateId: "a", rrfRank: 2 }, { contextId: "a" }),
        candidate({ candidateId: "b", rrfRank: 1 }, { contextId: "b" }),
        candidate({ candidateId: "c", rrfRank: 3 }, { contextId: "c" }),
      ];
      const first = reranker.rerank("liquidity risk", candidates, noAnalysis);
      const second = reranker.rerank("liquidity risk", candidates, noAnalysis);
      expect(first.map((c) => c.candidateId)).toEqual(second.map((c) => c.candidateId));
      expect(first.map((c) => c.relevanceRank)).toEqual([1, 2, 3]);
    },
  );
});
