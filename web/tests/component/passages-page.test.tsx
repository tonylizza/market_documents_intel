/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PassageFilterOptions, PassageSearchResult } from "@/lib/domain/passage";

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
});
