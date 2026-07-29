/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageResultCard } from "@/components/PassageResultCard";
import type { PassageSearchResult } from "@/lib/domain/passage";

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
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    heading: "Liquidity and going concern",
    headingHighlight: [{ text: "Liquidity", matched: true }, { text: " and going concern", matched: false }],
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    firstPageNumber: 10,
    lastPageNumber: 10,
    wordCount: 40,
    primaryNarrativeEligible: true,
    featureEligible: true,
    excerpt: [{ text: "The group maintains adequate ", matched: false }, { text: "liquidity", matched: true }, { text: " headroom.", matched: false }],
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

describe("PassageResultCard", () => {
  it("shows company, ticker, period, and page range", () => {
    render(<PassageResultCard result={makeResult()} />);
    expect(screen.getByText(/Acme Corp \(ACT\)/)).toBeInTheDocument();
    expect(screen.getByText(/Page 10/)).toBeInTheDocument();
  });

  it("shows the alignment status and confidence labels, never raw enum values", () => {
    render(<PassageResultCard result={makeResult()} />);
    expect(screen.getByText("Unchanged")).toBeInTheDocument();
    expect(screen.getByText("High confidence")).toBeInTheDocument();
    expect(screen.queryByText("UNCHANGED")).not.toBeInTheDocument();
  });

  it("highlights matched terms in both the heading and the excerpt", () => {
    render(<PassageResultCard result={makeResult()} />);
    const marks = document.querySelectorAll("mark");
    expect(marks.length).toBeGreaterThanOrEqual(2);
  });

  it("links to the passage-comparison detail page when one exists", () => {
    render(<PassageResultCard result={makeResult()} />);
    expect(screen.getByRole("link", { name: /view passage evidence/i })).toHaveAttribute("href", "/passages/pc1");
  });

  it("handles a report-only passage (no passageComparisonId) without a broken link or alignment badges", () => {
    render(
      <PassageResultCard
        result={makeResult({ passageComparisonId: null, reportComparisonId: null, alignmentStatus: null, confidence: null, confidenceLabel: null })}
      />,
    );
    expect(screen.getByText("No published alignment")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view company/i })).toHaveAttribute("href", "/companies/ACT");
  });

  it("renders a placeholder for a null heading", () => {
    render(<PassageResultCard result={makeResult({ heading: null, headingHighlight: null })} />);
    expect(screen.getByText("(No heading)")).toBeInTheDocument();
  });
});
