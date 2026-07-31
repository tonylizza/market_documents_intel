/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { QaPipelineResult } from "@/lib/services/qa/qa-orchestrator";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

let mockResult: QaPipelineResult | null = null;
let mockShouldThrow = false;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/services/qa/qa-orchestrator", () => ({
  runQaPipeline: async () => {
    if (mockShouldThrow) throw new Error("connection refused");
    return mockResult;
  },
}));

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: class {
    async listCompanies() {
      return [
        {
          id: "company-act",
          ticker: "ACT",
          name: "AfroCentric Investment Corporation Limited",
          sector: null,
          description: null,
          firstReportPeriodEnd: "2021-12-31",
          latestReportPeriodEnd: "2024-12-31",
          reportCount: 4,
          comparisonCount: 3,
          latestComparisonId: null,
          historicalPeakComparisonId: null,
          displayOrder: 0,
        },
      ];
    }
  },
}));

function evidence(overrides: Partial<QaEvidenceChunk["citation"]> = {}, chunkId = "chunk-1"): QaEvidenceChunk {
  const citation = {
    chunkId,
    companyId: "company-act",
    companyTicker: "ACT",
    companyName: "AfroCentric Investment Corporation Limited",
    reportId: "report-1",
    reportTitle: "2024 Annual Report",
    reportPeriodEnd: "2024-12-31",
    pageStart: 12,
    pageEnd: 14,
    sectionHeading: "Liquidity risk",
    memberPassageIds: ["p1"],
    label: "ACT, 2024 report, pp. 12-14",
    ...overrides,
  };
  return {
    chunkId,
    text: "The group maintains adequate liquidity headroom.",
    citation,
    similarity: 0.92,
    fusedScore: null,
    mergedCandidateCount: 1,
  };
}

function baseResult(overrides: Partial<QaPipelineResult> = {}): QaPipelineResult {
  return {
    route: "DOCUMENT_QA",
    analysis: {
      question: "What is ACT's liquidity position?",
      normalizedQuestion: "What is ACT's liquidity position?",
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
      directionalConcepts: [],
      quantitativeConcepts: [],
      causalConcepts: [],
      ambiguitySensitiveConcepts: [],
      unresolvedRequiredConcepts: [],
      optionalConceptFamilies: [],
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any,
    answer: {
      status: "ANSWERED",
      answerText: "ACT maintains adequate liquidity headroom [E1].",
      unsupportedPortion: null,
      citedEvidence: [evidence()],
      allEvidence: [evidence()],
      providerLatencyMs: 500,
      errorDetail: null,
    },
    comparisonLinkTicker: null,
    grouped: [],
    retrievalLatencyMs: 100,
    totalLatencyMs: 600,
    ...overrides,
  };
}

describe("AskPage", () => {
  it("shows an empty state prompt when no question is asked", async () => {
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({}) });
    render(ui);
    expect(screen.getByText("Enter a question to get a grounded answer")).toBeInTheDocument();
  });

  it("renders an ANSWERED answer with citations", async () => {
    mockResult = baseResult();
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity position?" }) });
    render(ui);
    expect(await screen.findByText("Answered from the report excerpts below")).toBeInTheDocument();
    expect(screen.getByText(/ACT maintains adequate liquidity headroom/)).toBeInTheDocument();
    expect(screen.getByText("ACT, 2024 report, pp. 12-14")).toBeInTheDocument();
  });

  it("renders INSUFFICIENT_EVIDENCE state without an answer", async () => {
    mockResult = baseResult({
      answer: {
        status: "INSUFFICIENT_EVIDENCE",
        answerText: null,
        unsupportedPortion: null,
        citedEvidence: [],
        allEvidence: [],
        providerLatencyMs: null,
        errorDetail: null,
      },
    });
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What does the company disclose about esports?" }) });
    render(ui);
    expect(await screen.findByText("Not enough evidence to answer this question")).toBeInTheDocument();
    expect(screen.getByText("No supporting excerpts were retrieved for this question.")).toBeInTheDocument();
  });

  it("renders PROVIDER_UNAVAILABLE state with evidence still shown, no invented answer", async () => {
    mockResult = baseResult({
      answer: {
        status: "PROVIDER_UNAVAILABLE",
        answerText: null,
        unsupportedPortion: null,
        citedEvidence: [],
        allEvidence: [evidence()],
        providerLatencyMs: 200,
        errorDetail: "Gemini returned HTTP 503.",
      },
    });
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity position?" }) });
    render(ui);
    expect(await screen.findByText("The answer generator is temporarily unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/ACT maintains adequate liquidity headroom/)).not.toBeInTheDocument();
    // Evidence is still shown even though generation failed.
    expect(screen.getByText("ACT, 2024 report, pp. 12-14")).toBeInTheDocument();
  });

  it("renders PARTIALLY_ANSWERED with the unsupported portion explicit", async () => {
    mockResult = baseResult({
      answer: {
        status: "PARTIALLY_ANSWERED",
        answerText: "ACT discusses liquidity but not covenant compliance [E1].",
        unsupportedPortion: "The excerpts do not address covenant compliance specifically.",
        citedEvidence: [evidence()],
        allEvidence: [evidence()],
        providerLatencyMs: 400,
        errorDetail: null,
      },
    });
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What is ACT's covenant compliance status?" }) });
    render(ui);
    expect(await screen.findByText("Partially answered -- see what's missing below")).toBeInTheDocument();
    expect(screen.getByText(/covenant compliance specifically/)).toBeInTheDocument();
  });

  it("shows an error state when the pipeline throws", async () => {
    mockShouldThrow = true;
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity position?" }) });
    render(ui);
    expect(screen.getByText("Ask is temporarily unavailable")).toBeInTheDocument();
    mockShouldThrow = false;
  });

  it("marks the answer status banner as an accessible live region", async () => {
    mockResult = baseResult();
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "What is ACT's liquidity position?" }) });
    render(ui);
    const banner = await screen.findByRole("status");
    expect(banner).toHaveAttribute("aria-live", "polite");
  });

  it("labels the question input and renders the Ask button", async () => {
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({}) });
    render(ui);
    expect(screen.getByLabelText("Question")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeInTheDocument();
  });

  it("shows the route badge for the classified question type", async () => {
    mockResult = baseResult({ route: "COMPARISON_QA", comparisonLinkTicker: "ACT" });
    const { default: AskPage } = await import("@/app/ask/page");
    const ui = await AskPage({ searchParams: Promise.resolve({ q: "Did ACT's liquidity risk increase since last year?" }) });
    render(ui);
    expect(screen.getByText("Comparison / change-over-time question")).toBeInTheDocument();
    expect(screen.getByText(/View ACT's full comparison timeline/)).toBeInTheDocument();
  });
});
