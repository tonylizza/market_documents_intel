import { describe, expect, it } from "vitest";
import { computeDirectResponsiveness, enrichWithDirectResponsiveness, FULL_GATE_STRATEGY_CONFIG, type DirectResponsivenessStrategyConfig } from "@/lib/services/qa/direct-responsiveness";
import type { EvidenceCandidate, QueryAnalysis, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";
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
    heading: "Foreign exchange exposure",
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
    text: "The group's exposure to foreign exchange movements is hedged through forward contracts.",
    categories: ["financial_condition"],
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

function analysis(overrides: Partial<QueryAnalysis> = {}): QueryAnalysis {
  return {
    question: "What foreign exchange exposure does ACT have?",
    normalizedQuestion: "What foreign exchange exposure does ACT have?",
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
    requiredConceptFamilies: ["foreign_exchange"],
    optionalConceptFamilies: [],
    directionalConcepts: [],
    quantitativeConcepts: [],
    causalConcepts: [],
    ambiguitySensitiveConcepts: [],
    unresolvedRequiredConcepts: [],
    ...overrides,
  };
}

describe("computeDirectResponsiveness -- scoring formula", () => {
  it("scores a full body match at the required-coverage weight (0.8) with no penalty", () => {
    const result = computeDirectResponsiveness(candidate(), analysis());
    expect(result.conceptCoverageScore).toBeCloseTo(0.8, 5);
    expect(result.directResponsivenessScore).toBeCloseTo(0.8, 5);
    expect(result.eligible).toBe(true);
    expect(result.ineligibilityReasons).toEqual([]);
  });

  it("applies the generic-language penalty to a company-only match, dropping it below the floor", () => {
    const c = candidate({}, { heading: "Board composition", text: "The board comprises five non-executive directors." });
    const result = computeDirectResponsiveness(c, analysis());
    expect(result.eligible).toBe(false);
    expect(result.ineligibilityReasons).toContain("COMPANY_ONLY_MATCH");
    expect(result.directResponsivenessScore).toBeLessThan(FULL_GATE_STRATEGY_CONFIG.directResponsivenessFloor);
  });

  it("requires a body match (not heading-only) under requireBodyMatch:true", () => {
    const c = candidate({}, { heading: "Foreign exchange exposure", text: "The group maintains adequate liquidity headroom." });
    const result = computeDirectResponsiveness(c, analysis());
    expect(result.ineligibilityReasons).toContain("BODY_SUPPORT_MISSING");
    expect(result.eligible).toBe(false);
  });

  it("does not require a body match when requireBodyMatch is disabled", () => {
    const c = candidate({}, { heading: "Foreign exchange exposure", text: "The group maintains adequate liquidity headroom." });
    const lenient: DirectResponsivenessStrategyConfig = { ...FULL_GATE_STRATEGY_CONFIG, requireBodyMatch: false };
    const result = computeDirectResponsiveness(c, analysis(), lenient);
    expect(result.ineligibilityReasons).not.toContain("BODY_SUPPORT_MISSING");
  });

  it("zeroes the score when a quantitative question's candidate has no number", () => {
    const c = candidate({}, { text: "The group incurred a loss for the year, driven by lower revenue." });
    const result = computeDirectResponsiveness(c, analysis({ requiredConceptFamilies: [], quantitativeConcepts: ["quantitative"] }));
    expect(result.directResponsivenessScore).toBe(0);
    expect(result.ineligibilityReasons).toContain("QUANTITATIVE_REQUIREMENT_UNMET");
    expect(result.eligible).toBe(false);
  });

  it("is deterministic -- identical input produces identical output", () => {
    const a = computeDirectResponsiveness(candidate(), analysis());
    const b = computeDirectResponsiveness(candidate(), analysis());
    expect(a).toEqual(b);
  });
});

describe("enrichWithDirectResponsiveness -- ranking and ties", () => {
  function reranked(overrides: Partial<RerankedEvidenceCandidate> = {}, contextOverrides: Partial<RetrievalContext> = {}): RerankedEvidenceCandidate {
    return {
      ...candidate({}, contextOverrides),
      relevanceScore: 0.5,
      relevanceRank: 1,
      rerankerMethod: "baseline",
      numericFragmentSeverity: null,
      conceptCoverageScore: 0,
      directResponsivenessScore: 0,
      directResponsivenessRank: 0,
      evidenceEligible: false,
      ineligibilityReasons: [],
      ...overrides,
    };
  }

  it("preserves the original relevanceRank order when drivesRanking is false", () => {
    const a = reranked({ candidateId: "a", relevanceRank: 1 }, { contextId: "a", passageId: "p-a" });
    const b = reranked({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "p-b" });
    const enriched = enrichWithDirectResponsiveness([b, a], analysis(), FULL_GATE_STRATEGY_CONFIG, false);
    expect(enriched.map((c) => c.candidateId)).toEqual(["a", "b"]);
    expect(enriched[0].relevanceRank).toBe(1);
  });

  it("re-sorts by directResponsivenessScore when drivesRanking is true, with a stable candidateId tie-break", () => {
    const strong = reranked({ candidateId: "b", relevanceRank: 2 }, { contextId: "b", passageId: "p-b" });
    const weak = reranked(
      { candidateId: "a", relevanceRank: 1 },
      { contextId: "a", passageId: "p-a", heading: "Board composition", text: "The board comprises five non-executive directors." },
    );
    const enriched = enrichWithDirectResponsiveness([weak, strong], analysis(), FULL_GATE_STRATEGY_CONFIG, true);
    expect(enriched[0].candidateId).toBe("b");
    expect(enriched[0].directResponsivenessRank).toBe(1);
    expect(enriched[0].relevanceRank).toBe(1);
  });
});
