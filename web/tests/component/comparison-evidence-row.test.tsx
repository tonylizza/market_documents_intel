/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonEvidenceRow } from "@/components/ComparisonEvidenceRow";
import type { ComparisonEvidenceItem } from "@/lib/domain/passage";

function makeItem(overrides: Partial<ComparisonEvidenceItem> = {}): ComparisonEvidenceItem {
  return {
    passageComparisonId: "pc1",
    alignmentStatus: "SUBSTANTIALLY_MODIFIED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    collisionFlag: true,
    splitMergeFlag: false,
    contentScore: 0.7,
    earlier: { passageId: "p1", heading: "Impairment", excerpt: [{ text: "earlier text", matched: false }], firstPageNumber: 5, lastPageNumber: 5, wordCount: 20 },
    later: { passageId: "p2", heading: "Impairment review", excerpt: [{ text: "later text", matched: false }], firstPageNumber: 40, lastPageNumber: 41, wordCount: 25 },
    ...overrides,
  };
}

describe("ComparisonEvidenceRow", () => {
  it("shows both sides' headings and excerpts", () => {
    render(<ComparisonEvidenceRow item={makeItem()} />);
    expect(screen.getByText("Impairment")).toBeInTheDocument();
    expect(screen.getByText("Impairment review")).toBeInTheDocument();
    expect(screen.getByText("earlier text")).toBeInTheDocument();
    expect(screen.getByText("later text")).toBeInTheDocument();
  });

  it("shows the collision-flagged badge when set", () => {
    render(<ComparisonEvidenceRow item={makeItem({ collisionFlag: true })} />);
    expect(screen.getByText("Collision flagged")).toBeInTheDocument();
  });

  it("explains a missing side (NEW: no earlier passage)", () => {
    render(<ComparisonEvidenceRow item={makeItem({ alignmentStatus: "NEW", earlier: null })} />);
    expect(screen.getByText(/No aligned earlier passage/)).toBeInTheDocument();
  });

  it("links to the full passage-comparison detail page", () => {
    render(<ComparisonEvidenceRow item={makeItem()} />);
    expect(screen.getByRole("link", { name: /view full passage evidence/i })).toHaveAttribute("href", "/passages/pc1");
  });

  it("keeps the content score inside collapsed technical details, not inline", () => {
    render(<ComparisonEvidenceRow item={makeItem()} />);
    const details = screen.getByText("Technical details").closest("details");
    expect(details).not.toHaveAttribute("open");
  });
});
