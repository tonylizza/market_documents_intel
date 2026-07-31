import { describe, expect, it } from "vitest";
import { buildEvidencePackage, EVIDENCE_SELECTION_VERSION, type BuildEvidencePackageInput } from "@/lib/services/qa/evidence-package";
import type { EvidenceCoherence, EvidenceSet, GateDecision, QueryAnalysis, SelectedEvidence } from "@/lib/domain/qa-evidence";
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

function evidence(): SelectedEvidence {
  const ctx = context();
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
  };
}

function analysis(): QueryAnalysis {
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

function baseInput(overrides: Partial<BuildEvidencePackageInput> = {}): BuildEvidencePackageInput {
  const gateDecision: GateDecision = {
    status: "SUPPORTED",
    reasonCodes: ["SUPPORTED_BY_SINGLE_PASSAGE"],
    signals: {
      distinctPassageCount: 1,
      strongEvidenceCount: 1,
      requiredScopeSatisfied: true,
      requiredSideSatisfied: true,
      citationComplete: true,
      topicCoverageRatio: 1,
      topScoreMargin: Number.POSITIVE_INFINITY,
      numericFragmentWithoutContextRatio: 0,
      redundancyRatio: 0,
      contradictionDetected: false,
      directlyResponsiveCount: 1,
    },
    supportedSubquestions: ["What is ACT's liquidity risk?"],
    unsupportedSubquestions: [],
    partialSupportRationale: "The question's single element is directly supported by selected evidence.",
  };
  const evidenceSet: EvidenceSet = {
    selected: [evidence()],
    rejected: [
      { candidateId: "d1", passageId: "p-d1", retrievalContextId: "ctx-d1", reason: "DUPLICATE" },
      { candidateId: "d2", passageId: "p-d2", retrievalContextId: "ctx-d2", reason: "DUPLICATE" },
      { candidateId: "s1", passageId: "p-s1", retrievalContextId: "ctx-s1", reason: "OUT_OF_SCOPE" },
    ],
    coverage: { requiredFacets: [], coveredFacets: [], coverageRatio: 1 },
  };
  return {
    publicationId: "pub-1",
    question: "What is ACT's liquidity risk?",
    analysis: analysis(),
    gateDecision,
    evidenceSet,
    coherence: noContradiction,
    candidateCount: 12,
    candidateSources: ["keyword", "semantic"],
    retrievalMode: "hybrid",
    rerankerMethod: "quality_aware",
    latencyMs: { queryAnalysis: 1, candidateGeneration: 2, reranking: 1, evidenceSetConstruction: 1, groundednessGate: 1, total: 6 },
    ...overrides,
  };
}

describe("buildEvidencePackage", () => {
  it("assembles the package with the correct version, status, and question fields", () => {
    const pkg = buildEvidencePackage(baseInput());
    expect(pkg.evidenceSelectionVersion).toBe(EVIDENCE_SELECTION_VERSION);
    expect(pkg.gateStatus).toBe("SUPPORTED");
    expect(pkg.gateReasonCodes).toEqual(["SUPPORTED_BY_SINGLE_PASSAGE"]);
    expect(pkg.question).toBe("What is ACT's liquidity risk?");
    expect(pkg.publicationId).toBe("pub-1");
  });

  it("groups rejected evidence by reason with correct counts", () => {
    const pkg = buildEvidencePackage(baseInput());
    expect(pkg.rejectedEvidenceSummary).toEqual(
      expect.arrayContaining([
        { reason: "DUPLICATE", count: 2 },
        { reason: "OUT_OF_SCOPE", count: 1 },
      ]),
    );
  });

  it("defaults publicationId to an empty string when none is active", () => {
    const pkg = buildEvidencePackage(baseInput({ publicationId: null }));
    expect(pkg.publicationId).toBe("");
  });

  it("preserves full citation identity on every selected evidence item", () => {
    const pkg = buildEvidencePackage(baseInput());
    expect(pkg.selectedEvidence[0].citation.retrievalContextId).toBe("ctx-1");
    expect(pkg.selectedEvidence[0].citation.label).toBe("ACT, p. 10");
  });

  it("produces a valid ISO timestamp for generatedAt", () => {
    const pkg = buildEvidencePackage(baseInput());
    expect(() => new Date(pkg.generatedAt).toISOString()).not.toThrow();
    expect(new Date(pkg.generatedAt).toISOString()).toBe(pkg.generatedAt);
  });

  it("never includes a raw embedding vector anywhere in the package", () => {
    const pkg = buildEvidencePackage(baseInput());
    const serialized = JSON.stringify(pkg);
    expect(serialized).not.toMatch(/"embedding"\s*:/);
    expect(serialized).not.toMatch(/"vector"\s*:/);
  });

  it("never includes database credentials anywhere in the package", () => {
    const pkg = buildEvidencePackage(baseInput());
    const serialized = JSON.stringify(pkg).toLowerCase();
    expect(serialized).not.toMatch(/password|connectionstring|database_url/);
  });

  it("carries the latency breakdown through unchanged", () => {
    const pkg = buildEvidencePackage(baseInput());
    expect(pkg.latencyMs.total).toBe(6);
  });
});
