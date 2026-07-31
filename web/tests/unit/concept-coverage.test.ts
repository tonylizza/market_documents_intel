import { describe, expect, it } from "vitest";
import { computeConceptCoverage } from "@/lib/services/qa/concept-coverage";
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

describe("computeConceptCoverage -- body vs heading weighting", () => {
  it("counts a required family matched in the passage body at full weight", () => {
    const coverage = computeConceptCoverage(candidate(), analysis());
    expect(coverage.matchedRequiredFamilies).toEqual(["foreign_exchange"]);
    expect(coverage.matchLocationByFamily.foreign_exchange).toBe("body");
    expect(coverage.weightedRequiredCoverage).toBe(1);
    expect(coverage.hasBodyMatch).toBe(true);
  });

  it("counts a heading-only match at the reduced weight, not full weight", () => {
    const c = candidate({}, { heading: "Foreign exchange exposure", text: "The group maintains adequate liquidity headroom." });
    const coverage = computeConceptCoverage(c, analysis());
    expect(coverage.matchedRequiredFamilies).toEqual(["foreign_exchange"]);
    expect(coverage.matchLocationByFamily.foreign_exchange).toBe("heading_only");
    expect(coverage.weightedRequiredCoverage).toBeCloseTo(0.4, 5);
    expect(coverage.hasBodyMatch).toBe(false);
  });

  it("reports the family as missing when neither heading nor body match", () => {
    const c = candidate({}, { heading: "Board composition", text: "The board comprises five non-executive directors." });
    const coverage = computeConceptCoverage(c, analysis());
    expect(coverage.matchedRequiredFamilies).toEqual([]);
    expect(coverage.missingRequiredFamilies).toEqual(["foreign_exchange"]);
    expect(coverage.weightedRequiredCoverage).toBe(0);
  });
});

describe("computeConceptCoverage -- company-only, scope-only, and generic-only indicators", () => {
  it("flags companyOnlyIndicator when the right company is present but nothing substantive matches", () => {
    const c = candidate({}, { heading: "Board composition", text: "The board comprises five non-executive directors." });
    const coverage = computeConceptCoverage(c, analysis());
    expect(coverage.genericOnlyIndicator).toBe(true);
    expect(coverage.companyOnlyIndicator).toBe(true);
    expect(coverage.scopeOnlyIndicator).toBe(true);
  });

  it("does not flag companyOnlyIndicator for the wrong company (no scope match at all)", () => {
    const c = candidate({}, { companyTicker: "SBP", heading: "Board composition", text: "The board comprises five non-executive directors." });
    const coverage = computeConceptCoverage(c, analysis());
    expect(coverage.companyOnlyIndicator).toBe(false);
    expect(coverage.scopeOnlyIndicator).toBe(false);
    expect(coverage.genericOnlyIndicator).toBe(true);
  });

  it("does not flag generic-only when a genuine required-family match exists", () => {
    const coverage = computeConceptCoverage(candidate(), analysis());
    expect(coverage.genericOnlyIndicator).toBe(false);
    expect(coverage.companyOnlyIndicator).toBe(false);
    expect(coverage.scopeOnlyIndicator).toBe(false);
  });
});

describe("computeConceptCoverage -- directional/quantitative/causal coverage", () => {
  it("requires a digit in the body for quantitative coverage", () => {
    const withNumber = candidate({}, { text: "Net loss for the year was USD 3,144,172." });
    const withoutNumber = candidate({}, { text: "The group incurred a loss for the year." });
    const a = analysis({ quantitativeConcepts: ["quantitative"] });
    expect(computeConceptCoverage(withNumber, a).quantitativeCoverage).toBe(true);
    expect(computeConceptCoverage(withoutNumber, a).quantitativeCoverage).toBe(false);
  });

  it("maps 'added'/'removed' directional concepts to alignment status, not free text", () => {
    const added = candidate({}, { alignmentStatus: "NEW" });
    const a = analysis({ directionalConcepts: ["added"] });
    expect(computeConceptCoverage(added, a).directionalCoverage).toBe(true);
    const unchanged = candidate({}, { alignmentStatus: "UNCHANGED" });
    expect(computeConceptCoverage(unchanged, a).directionalCoverage).toBe(false);
  });

  it("requires an explanatory pattern for causal coverage", () => {
    const explained = candidate({}, { text: "Operating margin declined because of higher input costs." });
    const bare = candidate({}, { text: "Operating margin declined." });
    const a = analysis({ causalConcepts: ["causal"] });
    expect(computeConceptCoverage(explained, a).causalCoverage).toBe(true);
    expect(computeConceptCoverage(bare, a).causalCoverage).toBe(false);
  });
});
