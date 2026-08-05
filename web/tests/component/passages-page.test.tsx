/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PassageFilterOptions, PassageSearchResult } from "@/lib/domain/passage";
import type { GroupedRetrievalResult, RetrievalPage } from "@/lib/domain/retrieval";

const FILTER_OPTIONS: PassageFilterOptions = {
  companies: [{ value: "ACT", label: "Acme Corp (ACT)" }],
  alignmentStatuses: [{ value: "NEW", label: "New" }],
  confidenceLevels: [{ value: "HIGH", label: "High confidence" }],
  passageTypes: [{ value: "LIST", label: "List" }],
  categories: [{ value: "risk", label: "Risk" }],
  subcategoriesByCategory: {},
  reportSideQualities: [],
  alignmentChangeQualities: [],
};

function makeResult(overrides: Partial<PassageSearchResult> = {}): PassageSearchResult {
  return {
    passageId: "p1",
    passageComparisonId: "pc1",
    reportComparisonId: "rc1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    reportId: "r1",
    reportPeriodEnd: "2024-06-30",
    reportSide: "LATER",
    earlierPeriodEnd: null,
    laterPeriodEnd: null,
    heading: "Liquidity and going concern",
    headingHighlight: [{ text: "Liquidity", matched: true }],
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    firstPageNumber: 1,
    lastPageNumber: 1,
    wordCount: 10,
    primaryNarrativeEligible: true,
    featureEligible: true,
    excerpt: [{ text: "liquidity excerpt text", matched: true }],
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    collisionFlag: false,
    splitMergeFlag: false,
    rank: 0.8,
    ...overrides,
  };
}

let searchResults: PassageSearchResult[] = [];
let shouldThrow = false;

vi.mock("@/lib/repositories/postgres-passage-repository", () => ({
  PostgresPassageRepository: class {
    async searchPassages() {
      if (shouldThrow) throw new Error("connection refused");
      return searchResults;
    }
    async countPassageSearchResults() {
      if (shouldThrow) throw new Error("connection refused");
      return { count: searchResults.length, capped: false };
    }
    async getPassageFilterOptions() {
      if (shouldThrow) throw new Error("connection refused");
      return FILTER_OPTIONS;
    }
  },
}));

function makeGroupedResult(overrides: Partial<GroupedRetrievalResult> = {}): GroupedRetrievalResult {
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
      modelRevision: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
      strength: "strong",
    },
    evidenceUrl: "/passages/pc-1",
    passageDetailUrl: "/passages/pc-1",
    finalRank: 1,
    hasAdditionalContexts: false,
    ...overrides,
  };
}

let retrievalPageResult: RetrievalPage = {
  results: [makeGroupedResult()],
  mode: "semantic",
  weakMatchNotice: false,
  providerUnavailable: false,
};

vi.mock("@/lib/services/retrieval-service", () => ({
  searchSemantic: async () => retrievalPageResult,
  searchHybrid: async () => retrievalPageResult,
}));

vi.mock("@/lib/services/query-embedding-provider", () => ({
  HttpQueryEmbeddingProvider: class {},
  CachingQueryEmbeddingProvider: class {},
  loadHttpQueryEmbeddingProviderConfig: () => ({
    serviceUrl: "http://localhost:8081",
    timeoutMs: 8000,
    expectedModel: "BAAI/bge-small-en-v1.5",
    expectedModelRevision: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    expectedDimensions: 384,
  }),
  queryEmbeddingCacheKeyPrefix: () => "test-prefix",
  createQueryEmbeddingProvider: () => ({ embedQuery: async () => ({}) }),
}));

vi.mock("@/lib/repositories/postgres-semantic-retrieval-repository", () => ({
  PostgresSemanticRetrievalRepository: class {},
}));

const { default: PassagesPage } = await import("@/app/passages/page");

describe("/passages page", () => {
  it("shows the orientation/empty state when no query or filter is present (never dumps the corpus)", async () => {
    searchResults = [makeResult()];
    shouldThrow = false;
    const jsx = await PassagesPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getByText(/Enter a search term or choose a filter to begin/)).toBeInTheDocument();
    expect(screen.queryByText("Liquidity and going concern")).not.toBeInTheDocument();
  });

  it("shows results for a lexical query", async () => {
    searchResults = [makeResult()];
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity" }) });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Liquidity and going concern" })).toBeInTheDocument();
  });

  it("shows results for a structured filter with no query", async () => {
    searchResults = [makeResult()];
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ company: "ACT" }) });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Liquidity and going concern" })).toBeInTheDocument();
  });

  it("shows the no-results state for a query that matches nothing", async () => {
    searchResults = [];
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "nonexistentterm" }) });
    render(jsx);
    expect(screen.getByText("No results for these filters")).toBeInTheDocument();
  });

  it("renders a safe error state when the database is unavailable (never a misleading zero-results message)", async () => {
    shouldThrow = true;
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity" }) });
    render(jsx);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText("No results for these filters")).not.toBeInTheDocument();
    shouldThrow = false;
  });

  it("normalizes an invalid parameter instead of crashing", async () => {
    searchResults = [makeResult()];
    const jsx = await PassagesPage({
      searchParams: Promise.resolve({ q: "liquidity", status: "not-a-real-status", page: "-5", sort: "drop-table" }),
    });
    expect(() => render(jsx)).not.toThrow();
  });

  it("renders semantic-mode results with a semantic result card", async () => {
    retrievalPageResult = { results: [makeGroupedResult()], mode: "semantic", weakMatchNotice: false, providerUnavailable: false };
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity", mode: "semantic" }) });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Liquidity risk" })).toBeInTheDocument();
    expect(screen.getByText("Technical details")).toBeInTheDocument();
  });

  it("renders hybrid-mode results with a fused-score result card", async () => {
    retrievalPageResult = {
      results: [makeGroupedResult({ diagnostics: { ...makeGroupedResult().diagnostics, mode: "hybrid", fusedScore: 0.03, lexicalRankPosition: 2 } })],
      mode: "hybrid",
      weakMatchNotice: false,
      providerUnavailable: false,
    };
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity", mode: "hybrid" }) });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Liquidity risk" })).toBeInTheDocument();
  });

  it("shows a weak-match notice without describing similarity as a probability", async () => {
    retrievalPageResult = {
      results: [makeGroupedResult({ diagnostics: { ...makeGroupedResult().diagnostics, strength: "weak" } })],
      mode: "semantic",
      weakMatchNotice: true,
      providerUnavailable: false,
    };
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "obscure query", mode: "semantic" }) });
    render(jsx);
    expect(screen.getByText(/No strong semantic matches were found/)).toBeInTheDocument();
    expect(screen.queryByText(/% confident/)).not.toBeInTheDocument();
    expect(screen.queryByText(/\d+% match/)).not.toBeInTheDocument();
  });

  it("shows a provider-unavailable state distinct from the generic error state", async () => {
    retrievalPageResult = { results: [], mode: "semantic", weakMatchNotice: false, providerUnavailable: true };
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity", mode: "semantic" }) });
    render(jsx);
    expect(screen.getByText(/Semantic search is temporarily unavailable/)).toBeInTheDocument();
  });

  it("requires a query for semantic mode -- structured filters alone show an orientation state", async () => {
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ company: "ACT", mode: "semantic" }) });
    render(jsx);
    expect(screen.getByText(/Enter a search term to begin/)).toBeInTheDocument();
  });

  it("falls back to keyword mode for an invalid mode value", async () => {
    searchResults = [makeResult()];
    const jsx = await PassagesPage({ searchParams: Promise.resolve({ q: "liquidity", mode: "not-a-real-mode" }) });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Liquidity and going concern" })).toBeInTheDocument();
  });
});
