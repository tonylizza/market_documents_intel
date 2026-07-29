/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageResultsList } from "@/components/PassageResultsList";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import type { PassageSearchPage, PassageSearchResult } from "@/lib/domain/passage";

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
    heading: "Liquidity",
    headingHighlight: null,
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    firstPageNumber: 1,
    lastPageNumber: 1,
    wordCount: 10,
    primaryNarrativeEligible: true,
    featureEligible: true,
    excerpt: [{ text: "liquidity text", matched: false }],
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    collisionFlag: false,
    splitMergeFlag: false,
    rank: 0.5,
    ...overrides,
  };
}

function makePage(overrides: Partial<PassageSearchPage> = {}): PassageSearchPage {
  return {
    results: [makeResult()],
    pagination: { page: 1, pageSize: 25, totalCount: 1, totalIsCapped: false, totalPages: 1, hasNextPage: false, hasPreviousPage: false },
    params: parsePassageSearchParams({ q: "liquidity" }),
    ...overrides,
  };
}

describe("PassageResultsList", () => {
  it("shows the no-results state for zero results", () => {
    render(<PassageResultsList page={makePage({ results: [] })} />);
    expect(screen.getByText("No results for these filters")).toBeInTheDocument();
  });

  it("announces the result count for screen readers", () => {
    render(<PassageResultsList page={makePage()} />);
    expect(screen.getByRole("status")).toHaveTextContent("1 result");
  });

  it("renders a card per result", () => {
    render(<PassageResultsList page={makePage({ results: [makeResult({ passageId: "p1" }), makeResult({ passageId: "p2", passageComparisonId: "pc2" })] })} />);
    expect(screen.getAllByText("Liquidity")).toHaveLength(2);
  });

  it("shows the capped-count message when the total is capped", () => {
    render(
      <PassageResultsList
        page={makePage({ pagination: { page: 1, pageSize: 25, totalCount: 1000, totalIsCapped: true, totalPages: 40, hasNextPage: true, hasPreviousPage: false } })}
      />,
    );
    expect(screen.getByText(/1,000\+ results/)).toBeInTheDocument();
  });

  it("renders pagination when there is more than one page", () => {
    render(
      <PassageResultsList
        page={makePage({ pagination: { page: 1, pageSize: 25, totalCount: 60, totalIsCapped: false, totalPages: 3, hasNextPage: true, hasPreviousPage: false } })}
      />,
    );
    expect(screen.getByRole("navigation")).toBeInTheDocument();
  });
});
