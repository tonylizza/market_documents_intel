/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RetrievalResultsList } from "@/components/RetrievalResultsList";
import type { GroupedRetrievalResult, RetrievalPage } from "@/lib/domain/retrieval";

function makeResult(overrides: Partial<GroupedRetrievalResult> = {}): GroupedRetrievalResult {
  const context = {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED" as const,
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "KP2",
    companyName: "Kappa Two",
    reportSide: "LATER" as const,
    alignmentStatus: "UNCHANGED" as const,
    alignmentType: "ONE_TO_ONE" as const,
    confidence: "HIGH" as const,
    reportPeriodEnd: "2024-06-30",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    heading: "Liquidity risk",
    passageType: "PARAGRAPH" as const,
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    reportSideQuality: "GOOD" as const,
    alignmentChangeQuality: "GOOD" as const,
    collisionFlag: false,
    splitMergeFlag: false,
    irregularGapFlag: false,
    firstPageNumber: 10,
    lastPageNumber: 10,
    wordCount: 50,
    text: "The group maintains adequate liquidity headroom.",
    categories: [],
    riskSubcategories: [],
  };
  return {
    context,
    additionalContexts: [],
    excerpt: [{ text: "The group maintains adequate liquidity headroom.", matched: false }],
    headingHighlight: null,
    citation: {
      publicationId: "pub-1",
      retrievalContextId: "ctx-1",
      passageId: "passage-1",
      passageComparisonId: "pc-1",
      reportComparisonId: "rc-1",
      reportSide: "LATER",
      reportId: "report-1",
      firstPageNumber: 10,
      lastPageNumber: 10,
      label: "KP2, 2023->2024 comparison, later report, p. 10",
    },
    diagnostics: {
      mode: "semantic",
      vectorSearchMode: "hnsw",
      semanticSimilarity: 0.72,
      qualityFactor: 1,
      adjustedSemanticScore: 0.72,
      qualityExplanationCode: "NO_QUALITY_ADJUSTMENT",
      semanticRawRank: 1,
      semanticAdjustedRank: 1,
      lexicalRankPosition: null,
      fusedScore: null,
      model: "BAAI/bge-small-en-v1.5",
      modelRevision: "rev",
      strength: "strong",
    },
    evidenceUrl: "/passages/pc-1",
    passageDetailUrl: "/passages/pc-1",
    finalRank: 1,
    hasAdditionalContexts: false,
    ...overrides,
  };
}

function makePage(overrides: Partial<RetrievalPage> = {}): RetrievalPage {
  return { results: [makeResult()], mode: "semantic", weakMatchNotice: false, providerUnavailable: false, ...overrides };
}

describe("RetrievalResultsList", () => {
  it("renders a result count and result cards", () => {
    render(<RetrievalResultsList page={makePage()} />);
    expect(screen.getByText("1 result")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Liquidity risk" })).toBeInTheDocument();
  });

  it("shows the empty state when there are no results", () => {
    render(<RetrievalResultsList page={makePage({ results: [] })} />);
    expect(screen.getByText("No results for these filters")).toBeInTheDocument();
  });

  it("shows a provider-unavailable empty state distinct from the ordinary empty state", () => {
    render(<RetrievalResultsList page={makePage({ results: [], providerUnavailable: true })} />);
    expect(screen.getByText(/Semantic search is temporarily unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("No results for these filters")).not.toBeInTheDocument();
  });

  it("shows a weak-match notice alongside results, not instead of them", () => {
    render(<RetrievalResultsList page={makePage({ weakMatchNotice: true })} />);
    expect(screen.getByText(/No strong semantic matches were found/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Liquidity risk" })).toBeInTheDocument();
  });

  it("shows a degraded-service notice when providerUnavailable but lexical-only results exist", () => {
    render(<RetrievalResultsList page={makePage({ providerUnavailable: true })} />);
    expect(screen.getByText(/showing keyword-matched results only/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Liquidity risk" })).toBeInTheDocument();
  });
});
