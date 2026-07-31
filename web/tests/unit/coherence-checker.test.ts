import { describe, expect, it } from "vitest";
import { checkCoherence } from "@/lib/services/qa/coherence-checker";
import type { EvidenceRejection, QueryAnalysis, SelectedEvidence } from "@/lib/domain/qa-evidence";
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

describe("checkCoherence -- conflicting periods", () => {
  it("flags conflicting periods when a question with an explicit date range gets evidence from outside that scope", () => {
    const selected = [
      evidence({ candidateId: "a" }, { contextId: "a", reportPeriodEnd: "2021-12-31", laterPeriodEnd: "2021-12-31" }),
      evidence({ candidateId: "b" }, { contextId: "b", reportPeriodEnd: "2024-12-31", laterPeriodEnd: "2024-12-31" }),
    ];
    const result = checkCoherence(
      selected,
      [],
      analysis({ questionType: "descriptive", comparisonDirection: null, dateRange: { start: "2024-01-01", end: "2024-12-31" } }),
    );
    expect(result.conflictingPeriods).toBe(true);
    expect(result.hasContradiction).toBe(true);
  });

  it("does not flag an open-ended descriptive question (no explicit period) even when its evidence spans several report years", () => {
    // Real-corpus finding: a question like "what growth opportunities has
    // ACT identified" has no inherent period scope -- the same theme
    // recurring across a company's 2016 and 2024 reports is breadth, not
    // contradiction, unless the question itself narrowed to one period.
    const selected = [
      evidence({ candidateId: "a" }, { contextId: "a", reportPeriodEnd: "2016-06-30", laterPeriodEnd: "2016-06-30" }),
      evidence({ candidateId: "b" }, { contextId: "b", reportPeriodEnd: "2024-06-30", laterPeriodEnd: "2024-06-30" }),
    ];
    const result = checkCoherence(selected, [], analysis({ questionType: "descriptive", comparisonDirection: null, dateRange: null }));
    expect(result.conflictingPeriods).toBe(false);
  });

  it("does not flag conflicting periods for a comparative question that legitimately spans two periods", () => {
    const selected = [
      evidence({ candidateId: "a" }, { contextId: "a", reportSide: "EARLIER", reportPeriodEnd: null, earlierPeriodEnd: "2023-12-31", laterPeriodEnd: "2024-12-31" }),
      evidence({ candidateId: "b" }, { contextId: "b", reportSide: "LATER", reportPeriodEnd: null, earlierPeriodEnd: "2023-12-31", laterPeriodEnd: "2024-12-31" }),
    ];
    const result = checkCoherence(selected, [], analysis({ questionType: "comparative" }));
    expect(result.conflictingPeriods).toBe(false);
  });
});

describe("checkCoherence -- mixed alignment without explanation", () => {
  it("flags NEW and REMOVED evidence mixed with no explanatory link in either passage", () => {
    const selected = [
      evidence({ candidateId: "new" }, { contextId: "new", alignmentStatus: "NEW", text: "A newly introduced disclosure about risk." }),
      evidence({ candidateId: "removed" }, { contextId: "removed", alignmentStatus: "REMOVED", text: "A disclosure that is no longer present." }),
    ];
    const result = checkCoherence(selected, [], analysis());
    expect(result.mixedAlignmentWithoutExplanation).toBe(true);
    expect(result.hasContradiction).toBe(true);
  });

  it("does not flag mixed alignment when a selected passage explains the relationship", () => {
    const selected = [
      evidence({ candidateId: "new" }, { contextId: "new", alignmentStatus: "NEW", text: "A newly introduced disclosure about risk." }),
      evidence(
        { candidateId: "removed" },
        { contextId: "removed", alignmentStatus: "REMOVED", text: "This disclosure was reclassified into the new risk section above." },
      ),
    ];
    const result = checkCoherence(selected, [], analysis());
    expect(result.mixedAlignmentWithoutExplanation).toBe(false);
  });

  it("does not flag mixed alignment when only one of NEW/REMOVED is present", () => {
    const selected = [evidence({ candidateId: "new" }, { contextId: "new", alignmentStatus: "NEW" })];
    const result = checkCoherence(selected, [], analysis());
    expect(result.mixedAlignmentWithoutExplanation).toBe(false);
  });
});

describe("checkCoherence -- duplicate counted as independent", () => {
  it("flags when a duplicate's kept counterpart is actually in the selected set", () => {
    const selected = [evidence({ candidateId: "kept", passageId: "passage-1" }, { contextId: "kept", passageId: "passage-1" })];
    const rejected: EvidenceRejection[] = [{ candidateId: "dup", passageId: "passage-1", retrievalContextId: "dup-ctx", reason: "DUPLICATE" }];
    const result = checkCoherence(selected, rejected, analysis());
    expect(result.duplicateCountedAsIndependent).toBe(true);
  });

  it("does not flag when the duplicate's counterpart never made it into the selected set", () => {
    const selected = [evidence({ candidateId: "other", passageId: "passage-2" }, { contextId: "other", passageId: "passage-2" })];
    const rejected: EvidenceRejection[] = [{ candidateId: "dup", passageId: "passage-1", retrievalContextId: "dup-ctx", reason: "DUPLICATE" }];
    const result = checkCoherence(selected, rejected, analysis());
    expect(result.duplicateCountedAsIndependent).toBe(false);
  });

  it("does not treat a diagnosed duplicate as a contradiction on its own", () => {
    const selected = [evidence({ candidateId: "kept", passageId: "passage-1" }, { contextId: "kept", passageId: "passage-1" })];
    const rejected: EvidenceRejection[] = [{ candidateId: "dup", passageId: "passage-1", retrievalContextId: "dup-ctx", reason: "DUPLICATE" }];
    const result = checkCoherence(selected, rejected, analysis());
    expect(result.duplicateCountedAsIndependent).toBe(true);
    expect(result.hasContradiction).toBe(false);
  });
});

describe("checkCoherence -- out-of-range evidence", () => {
  it("flags a selected item outside the question's stated date range", () => {
    const selected = [evidence({}, { reportPeriodEnd: "2019-12-31", laterPeriodEnd: "2019-12-31" })];
    const result = checkCoherence(selected, [], analysis({ dateRange: { start: "2023-01-01", end: "2024-12-31" } }));
    expect(result.outOfRangeEvidence).toBe(true);
  });

  it("flags a selected item from a different company than the ones extracted", () => {
    const selected = [evidence({}, { companyTicker: "BEL" })];
    const result = checkCoherence(selected, [], analysis({ tickers: ["ACT"], requiredTicker: null }));
    expect(result.outOfRangeEvidence).toBe(true);
  });

  it("does not flag evidence squarely within the stated range and company", () => {
    const selected = [evidence({}, { companyTicker: "ACT", reportPeriodEnd: "2024-06-30", laterPeriodEnd: "2024-06-30" })];
    const result = checkCoherence(selected, [], analysis({ dateRange: { start: "2023-01-01", end: "2024-12-31" }, tickers: ["ACT"] }));
    expect(result.outOfRangeEvidence).toBe(false);
  });
});

describe("checkCoherence -- prefers ambiguity over assumed coherence", () => {
  it("returns hasContradiction=false only when no check found a problem (never a default 'assume coherent' override)", () => {
    const selected = [evidence()];
    const result = checkCoherence(selected, [], analysis());
    expect(result).toEqual({
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
    });
  });
});
