/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { EvidencePackage, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";
import type { RetrievalContext } from "@/lib/domain/retrieval";

let mockPackage: EvidencePackage;
const mockCandidates: RerankedEvidenceCandidate[] = [];
let mockShouldThrow = false;

vi.mock("@/lib/services/qa/qa-pipeline", () => ({
  runEvidencePipeline: async () => {
    if (mockShouldThrow) throw new Error("connection refused");
    return { evidencePackage: mockPackage, candidates: mockCandidates };
  },
}));

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
    categories: [],
    riskSubcategories: [],
    ...overrides,
  };
}

function basePackage(overrides: Partial<EvidencePackage> = {}): EvidencePackage {
  const ctx = context();
  return {
    evidenceSelectionVersion: "7b.1b.1",
    publicationId: "pub-1",
    question: "What is ACT's liquidity risk?",
    normalizedQuestion: "What is ACT's liquidity risk?",
    queryAnalysis: {
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
    },
    gateStatus: "SUPPORTED",
    gateReasonCodes: ["SUPPORTED_BY_SINGLE_PASSAGE"],
    selectedEvidence: [
      {
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
        rerankerMethod: "quality_aware",
        numericFragmentSeverity: null,
        conceptCoverageScore: 1,
        directResponsivenessScore: 1,
        directResponsivenessRank: 1,
        evidenceEligible: true,
        ineligibilityReasons: [],
        selectionOrder: 1,
        newFacetsCovered: [],
      },
    ],
    rejectedEvidenceSummary: [{ reason: "DUPLICATE", count: 2 }],
    coverage: { requiredFacets: [], coveredFacets: [], coverageRatio: 1 },
    supportedSubquestions: ["What is ACT's liquidity risk?"],
    unsupportedSubquestions: [],
    partialSupportRationale: "The question's single element is directly supported by selected evidence.",
    coherence: {
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
    },
    retrievalDiagnostics: { candidateCount: 12, sources: ["keyword", "semantic"], retrievalMode: "hybrid" },
    rerankerMethod: "quality_aware",
    generatedAt: new Date().toISOString(),
    latencyMs: { queryAnalysis: 1, candidateGeneration: 2, reranking: 1, evidenceSetConstruction: 1, groundednessGate: 1, total: 6 },
    ...overrides,
  };
}

describe("/evidence-review page", () => {
  it("prompts for a question when none is supplied", async () => {
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({}) });
    render(ui);
    expect(screen.getByText("Enter a question to review its evidence")).toBeInTheDocument();
  });

  it("displays query analysis, selected evidence, gate status, and citations for a question", async () => {
    mockPackage = basePackage();
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    render(ui);
    expect(await screen.findByText("Supported by the evidence below")).toBeInTheDocument();
    expect(screen.getByText("descriptive")).toBeInTheDocument();
    expect(screen.getByText("ACT")).toBeInTheDocument();
    expect(screen.getByText("Liquidity risk")).toBeInTheDocument();
    expect(screen.getByText("ACT, p. 10")).toBeInTheDocument();
  });

  it("shows rejected candidates with plain-language reasons", async () => {
    mockPackage = basePackage();
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    render(ui);
    expect(await screen.findByText(/Duplicate of another selected passage/)).toBeInTheDocument();
  });

  it("shows gate reasons in plain language, never a raw INSUFFICIENT_EVIDENCE-style code", async () => {
    mockPackage = basePackage({ gateStatus: "INSUFFICIENT_EVIDENCE", gateReasonCodes: ["NO_DIRECT_EVIDENCE"], selectedEvidence: [] });
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What does the company disclose about esports?" }) });
    render(ui);
    expect(await screen.findByText("Not enough evidence to answer")).toBeInTheDocument();
    expect(screen.queryByText("NO_DIRECT_EVIDENCE")).not.toBeInTheDocument();
    expect(screen.getByText("No passage in the corpus directly addresses this question.")).toBeInTheDocument();
  });

  it("never renders a generated answer -- only real passage excerpts and a gate verdict", async () => {
    mockPackage = basePackage();
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    const { container } = render(ui);
    expect(container.textContent).not.toMatch(/^Answer:/);
    expect(screen.queryByText(/^Based on the evidence, the answer is/)).not.toBeInTheDocument();
  });

  it("renders a safe error state when the pipeline is unavailable", async () => {
    mockShouldThrow = true;
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    render(ui);
    expect(await screen.findByText("Evidence review is temporarily unavailable")).toBeInTheDocument();
    mockShouldThrow = false;
  });

  it("shows candidate source and reranker method diagnostics", async () => {
    mockPackage = basePackage();
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    render(ui);
    expect(await screen.findByText(/12 candidates from keyword \+ semantic/)).toBeInTheDocument();
  });

  it("shows a latency figure", async () => {
    mockPackage = basePackage();
    const { default: EvidenceReviewPage } = await import("@/app/evidence-review/page");
    const ui = await EvidenceReviewPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity risk?" }) });
    render(ui);
    expect(await screen.findByText("6ms total")).toBeInTheDocument();
  });
});
