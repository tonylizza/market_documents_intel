import { describe, expect, it } from "vitest";
import { evaluateGroundedness } from "@/lib/services/qa/groundedness-gate";
import { getQaConfig, type QaConfig } from "@/lib/config/qa-config";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import type { EvidenceCoherence, EvidenceSet, QueryAnalysis, SelectedEvidence } from "@/lib/domain/qa-evidence";
import type { RetrievalContext } from "@/lib/domain/retrieval";

const FLOOR = getRetrievalConfig().minimumSemanticSimilarity;

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
    text: "The group maintains adequate liquidity headroom.",
    categories: [],
    riskSubcategories: [],
    ...overrides,
  };
}

function evidence(overrides: Partial<SelectedEvidence> = {}, contextOverrides: Partial<RetrievalContext> = {}): SelectedEvidence {
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
    selectionOrder: 1,
    newFacetsCovered: [],
    ...overrides,
  };
}

function evidenceSet(selected: SelectedEvidence[], rejected: EvidenceSet["rejected"] = [], coverageRatio = 1): EvidenceSet {
  return {
    selected,
    rejected,
    coverage: { requiredFacets: [], coveredFacets: [], coverageRatio },
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
    requiredTicker: null,
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

const noContradiction: EvidenceCoherence = {
  conflictingPeriods: false,
  mixedAlignmentWithoutExplanation: false,
  duplicateCountedAsIndependent: false,
  outOfRangeEvidence: false,
  hasContradiction: false,
  restatementAmbiguityDetected: false,
  restatementChronologyClear: null,
  supersededPassageIds: [],
  comparisonContextSatisfied: null,
  dateRangeCovered: null,
};

const config: QaConfig = getQaConfig();

describe("evaluateGroundedness -- Tier 1 (INSUFFICIENT_EVIDENCE)", () => {
  it("returns NO_DIRECT_EVIDENCE when there is no evidence and no hard requirement", () => {
    const decision = evaluateGroundedness(evidenceSet([]), analysis(), noContradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["NO_DIRECT_EVIDENCE"]);
  });

  it("returns REQUIRED_SCOPE_NOT_COVERED (not NO_DIRECT_EVIDENCE) when scope filtering actually rejected the candidates", () => {
    const outOfScopeRejections = [{ candidateId: "a", passageId: "p-a", retrievalContextId: "ctx-a", reason: "OUT_OF_SCOPE" as const }];
    const decision = evaluateGroundedness(evidenceSet([], outOfScopeRejections), analysis({ requiredTicker: "ACT" }), noContradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["REQUIRED_SCOPE_NOT_COVERED"]);
  });

  it("returns MISSING_COMPARISON_SIDE when scope filtering actually rejected the candidates for report side", () => {
    const outOfScopeRejections = [{ candidateId: "a", passageId: "p-a", retrievalContextId: "ctx-a", reason: "OUT_OF_SCOPE" as const }];
    const decision = evaluateGroundedness(
      evidenceSet([], outOfScopeRejections),
      analysis({ requiredReportSide: "LATER" }),
      noContradiction,
      config,
    );
    expect(decision.reasonCodes).toEqual(["MISSING_COMPARISON_SIDE"]);
  });

  it("returns both scope and side reasons when both were required and out-of-scope rejections actually occurred", () => {
    const outOfScopeRejections = [{ candidateId: "a", passageId: "p-a", retrievalContextId: "ctx-a", reason: "OUT_OF_SCOPE" as const }];
    const decision = evaluateGroundedness(
      evidenceSet([], outOfScopeRejections),
      analysis({ requiredTicker: "ACT", requiredReportSide: "LATER" }),
      noContradiction,
      config,
    );
    expect(decision.reasonCodes).toEqual(expect.arrayContaining(["REQUIRED_SCOPE_NOT_COVERED", "MISSING_COMPARISON_SIDE"]));
    expect(decision.reasonCodes).not.toContain("NO_DIRECT_EVIDENCE");
  });

  it("returns NO_DIRECT_EVIDENCE (not REQUIRED_SCOPE_NOT_COVERED) when a hard requirement was declared but everything was rejected for unrelated reasons", () => {
    // Real-data validation caught this: "What did ACT say about its ability
    // to continue operating?" had requiredTicker=ACT and 80 real ACT
    // candidates, but all 80 were rejected as DUPLICATE/BELOW_RELEVANCE_FLOOR
    // (never OUT_OF_SCOPE) -- the absence had nothing to do with scope, and
    // labeling it "scope not covered" would have been actively misleading.
    const unrelatedRejections = [
      { candidateId: "a", passageId: "p-a", retrievalContextId: "ctx-a", reason: "DUPLICATE" as const },
      { candidateId: "b", passageId: "p-b", retrievalContextId: "ctx-b", reason: "BELOW_RELEVANCE_FLOOR" as const },
    ];
    const decision = evaluateGroundedness(evidenceSet([], unrelatedRejections), analysis({ requiredTicker: "ACT" }), noContradiction, config);
    expect(decision.reasonCodes).toEqual(["NO_DIRECT_EVIDENCE"]);
  });

  it("returns CITATION_METADATA_INCOMPLETE when a selected item is missing citation fields", () => {
    const incomplete = evidence({ citation: { ...evidence().citation, reportId: "" } });
    const decision = evaluateGroundedness(evidenceSet([incomplete]), analysis(), noContradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["CITATION_METADATA_INCOMPLETE"]);
  });

  it("returns ONLY_WEAK_INDIRECT_EVIDENCE when the only evidence is a weak keyword rank with no semantic support", () => {
    const weak = evidence({ sources: ["keyword"], lexicalRankPosition: 25, semanticRawSimilarity: null });
    const decision = evaluateGroundedness(evidenceSet([weak]), analysis(), noContradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["ONLY_WEAK_INDIRECT_EVIDENCE"]);
  });

  it("returns NUMERIC_FRAGMENT_WITHOUT_CONTEXT when every selected item is a bare numeric fragment", () => {
    const fragment = evidence({ numericFragmentSeverity: "fragment_without_context" });
    const decision = evaluateGroundedness(evidenceSet([fragment]), analysis(), noContradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["NUMERIC_FRAGMENT_WITHOUT_CONTEXT"]);
  });
});

describe("evaluateGroundedness -- Tier 2 (AMBIGUOUS_OR_CONFLICTING)", () => {
  it("returns CONFLICTING_EVIDENCE when the coherence checker detected a contradiction", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const contradiction: EvidenceCoherence = { ...noContradiction, hasContradiction: true };
    const decision = evaluateGroundedness(evidenceSet([strong]), analysis(), contradiction, config);
    expect(decision.status).toBe("AMBIGUOUS_OR_CONFLICTING");
    expect(decision.reasonCodes).toEqual(["CONFLICTING_EVIDENCE"]);
  });
});

// Milestone 7B.1c Phase 6 tightens PARTIALLY_SUPPORTED for the shipped
// default (`strictPartialSupport: true`, on a single-element question,
// never reports PARTIALLY_SUPPORTED on vague coverage/margin/redundancy
// grounds alone -- see the "Tier 4" `PARTIAL_SUPPORT_NOT_SEPARABLE" tests
// below). These Tier 3 tests exercise the still-available legacy soft-
// signal path directly via the `weighted_gate` preset, which keeps
// `strictPartialSupport: false`.
const legacyConfig: QaConfig = { ...config, directResponsivenessPreset: "weighted_gate" };

describe("evaluateGroundedness -- Tier 3 (PARTIALLY_SUPPORTED, legacy soft-signal path)", () => {
  it("returns INSUFFICIENT_TOPIC_COVERAGE when coverage ratio is below the configured minimum", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const decision = evaluateGroundedness(evidenceSet([strong], [], legacyConfig.minTopicCoverageRatio - 0.01), analysis(), noContradiction, legacyConfig);
    expect(decision.status).toBe("PARTIALLY_SUPPORTED");
    expect(decision.reasonCodes).toContain("INSUFFICIENT_TOPIC_COVERAGE");
  });

  it("returns LOW_RELEVANCE_MARGIN when the top semantic score barely clears the weak-match floor", () => {
    const barelyAbove = evidence({
      sources: ["semantic"],
      lexicalRankPosition: null,
      semanticRawSimilarity: FLOOR + 0.001,
      semanticAdjustedScore: FLOOR + 0.001,
    });
    const decision = evaluateGroundedness(evidenceSet([barelyAbove]), analysis(), noContradiction, legacyConfig);
    expect(decision.status).toBe("PARTIALLY_SUPPORTED");
    expect(decision.reasonCodes).toContain("LOW_RELEVANCE_MARGIN");
  });

  it("never applies LOW_RELEVANCE_MARGIN to a keyword-only top result (no comparable cosine scale)", () => {
    const keywordOnly = evidence({ sources: ["keyword"], lexicalRankPosition: 1, semanticAdjustedScore: null });
    const decision = evaluateGroundedness(evidenceSet([keywordOnly]), analysis(), noContradiction, legacyConfig);
    expect(decision.reasonCodes).not.toContain("LOW_RELEVANCE_MARGIN");
  });

  it("returns EVIDENCE_REDUNDANT when the redundancy ratio exceeds the configured maximum", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const rejected: EvidenceSet["rejected"] = Array.from({ length: 10 }, (_, i) => ({
      candidateId: `r${i}`,
      passageId: `rp${i}`,
      retrievalContextId: `rctx${i}`,
      reason: "REDUNDANT_NO_NEW_COVERAGE" as const,
    }));
    const decision = evaluateGroundedness(evidenceSet([strong], rejected), analysis(), noContradiction, legacyConfig);
    expect(decision.status).toBe("PARTIALLY_SUPPORTED");
    expect(decision.reasonCodes).toContain("EVIDENCE_REDUNDANT");
  });

  it("returns a partial NUMERIC_FRAGMENT_WITHOUT_CONTEXT when only some selected items are bare numeric fragments", () => {
    const good = evidence({ candidateId: "good", numericFragmentSeverity: "none" }, { contextId: "good", passageId: "p-good" });
    const fragment = evidence(
      { candidateId: "fragment", numericFragmentSeverity: "fragment_without_context" },
      { contextId: "fragment", passageId: "p-fragment" },
    );
    const decision = evaluateGroundedness(evidenceSet([good, fragment]), analysis(), noContradiction, legacyConfig);
    expect(decision.status).toBe("PARTIALLY_SUPPORTED");
    expect(decision.reasonCodes).toContain("NUMERIC_FRAGMENT_WITHOUT_CONTEXT");
  });
});

// Milestone 7B.1c Phase 10: the shipped default preset
// (`query_type_gate_generic_penalty`) has `strictPartialSupport: false` --
// none of the 8 presets cleared every READY-FOR-7B.2 threshold, and this
// was the best available balance (see the final report). Strict-partial
// behavior (`PARTIAL_SUPPORT_NOT_SEPARABLE`) is exercised explicitly below
// via the strictest preset, not assumed to be the shipped default.
const strictConfig: QaConfig = { ...config, directResponsivenessPreset: "full_gate_restatement_safeguards" };

describe("evaluateGroundedness -- Tier 4 (SUPPORTED)", () => {
  it("returns plain SUPPORTED_BY_SINGLE_PASSAGE under the shipped (non-strict) default preset", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const decision = evaluateGroundedness(evidenceSet([strong]), analysis(), noContradiction, config);
    expect(decision.status).toBe("SUPPORTED");
    expect(decision.reasonCodes).toEqual(["SUPPORTED_BY_SINGLE_PASSAGE"]);
  });

  it("returns SUPPORTED_BY_MULTIPLE_PASSAGES when more than one distinct passage supports the answer", () => {
    const a = evidence({ candidateId: "a", sources: ["keyword"], lexicalRankPosition: 1 }, { contextId: "a", passageId: "p-a" });
    const b = evidence({ candidateId: "b", sources: ["keyword"], lexicalRankPosition: 2 }, { contextId: "b", passageId: "p-b" });
    const decision = evaluateGroundedness(evidenceSet([a, b]), analysis(), noContradiction, config);
    expect(decision.status).toBe("SUPPORTED");
    expect(decision.reasonCodes).toEqual(["SUPPORTED_BY_MULTIPLE_PASSAGES"]);
  });

  it("under a strict preset, always explains via PARTIAL_SUPPORT_NOT_SEPARABLE why a single-element question never lands in PARTIALLY_SUPPORTED", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const decision = evaluateGroundedness(evidenceSet([strong]), analysis(), noContradiction, strictConfig);
    expect(decision.status).toBe("SUPPORTED");
    expect(decision.reasonCodes).toEqual(["PARTIAL_SUPPORT_NOT_SEPARABLE", "SUPPORTED_BY_SINGLE_PASSAGE"]);
  });

  it("returns plain SUPPORTED_BY_SINGLE_PASSAGE (no PARTIAL_SUPPORT_NOT_SEPARABLE noise) under a non-strict preset", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const decision = evaluateGroundedness(evidenceSet([strong]), analysis(), noContradiction, legacyConfig);
    expect(decision.status).toBe("SUPPORTED");
    expect(decision.reasonCodes).toEqual(["SUPPORTED_BY_SINGLE_PASSAGE"]);
  });
});

describe("evaluateGroundedness -- tier precedence", () => {
  it("never reports CONFLICTING_EVIDENCE when there is no evidence at all, even if coherence flags a contradiction", () => {
    const contradiction: EvidenceCoherence = { ...noContradiction, hasContradiction: true };
    const decision = evaluateGroundedness(evidenceSet([]), analysis(), contradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).not.toContain("CONFLICTING_EVIDENCE");
  });

  it("prioritizes REQUIRED_SCOPE_NOT_COVERED over a would-be contradiction when there is no in-scope evidence", () => {
    const outOfScopeRejections = [{ candidateId: "a", passageId: "p-a", retrievalContextId: "ctx-a", reason: "OUT_OF_SCOPE" as const }];
    const contradiction: EvidenceCoherence = { ...noContradiction, hasContradiction: true };
    const decision = evaluateGroundedness(evidenceSet([], outOfScopeRejections), analysis({ requiredTicker: "ACT" }), contradiction, config);
    expect(decision.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(decision.reasonCodes).toEqual(["REQUIRED_SCOPE_NOT_COVERED"]);
  });

  it("prioritizes contradiction over partial-support signals (topic coverage) when evidence exists but conflicts", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const contradiction: EvidenceCoherence = { ...noContradiction, hasContradiction: true };
    const decision = evaluateGroundedness(evidenceSet([strong], [], 0.1), analysis(), contradiction, config);
    expect(decision.status).toBe("AMBIGUOUS_OR_CONFLICTING");
    expect(decision.reasonCodes).not.toContain("INSUFFICIENT_TOPIC_COVERAGE");
  });
});

describe("evaluateGroundedness -- determinism", () => {
  it("produces identical output across repeated calls with the same input", () => {
    const strong = evidence({ sources: ["keyword"], lexicalRankPosition: 1 });
    const first = evaluateGroundedness(evidenceSet([strong]), analysis(), noContradiction, config);
    const second = evaluateGroundedness(evidenceSet([strong]), analysis(), noContradiction, config);
    expect(first).toEqual(second);
  });
});

// Milestone 7B.1d (experimental): a chunk-only candidate (no keyword hit,
// no semantic hit of its own -- e.g. surfaced purely by mapping a Q&A
// retrieval-chunk child hit back to its parent passage) must be able to
// clear the same strong-evidence bar as a canonical semantic match, using
// the identical minimumSemanticSimilarity threshold -- never a looser one.
describe("evaluateGroundedness -- Milestone 7B.1d chunk-sourced strong evidence", () => {
  it("treats a chunk-only candidate above the similarity floor as strong evidence, avoiding ONLY_WEAK_INDIRECT_EVIDENCE", () => {
    const chunkOnly = evidence({
      sources: ["chunk"],
      lexicalRankPosition: null,
      semanticRawSimilarity: null,
      chunkStrategy: "LOCAL_WINDOW",
      chunkSimilarity: FLOOR + 0.05,
      chunkRawRank: 1,
      chunkHitCount: 1,
    });
    const decision = evaluateGroundedness(evidenceSet([chunkOnly]), analysis(), noContradiction, config);
    expect(decision.reasonCodes).not.toContain("ONLY_WEAK_INDIRECT_EVIDENCE");
  });

  it("still reports ONLY_WEAK_INDIRECT_EVIDENCE when the chunk-only candidate's similarity is below the floor", () => {
    const weakChunkOnly = evidence({
      sources: ["chunk"],
      lexicalRankPosition: null,
      semanticRawSimilarity: null,
      chunkStrategy: "LOCAL_WINDOW",
      chunkSimilarity: FLOOR - 0.05,
      chunkRawRank: 1,
      chunkHitCount: 1,
    });
    const decision = evaluateGroundedness(evidenceSet([weakChunkOnly]), analysis(), noContradiction, config);
    expect(decision.reasonCodes).toContain("ONLY_WEAK_INDIRECT_EVIDENCE");
  });
});
