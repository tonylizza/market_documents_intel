/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonEvidenceSummarySection } from "@/components/ComparisonEvidenceSummarySection";
import type { ComparisonEvidenceSummary } from "@/lib/domain/passage";

describe("ComparisonEvidenceSummarySection", () => {
  it("shows a count card for every one of the six statuses plus the total", () => {
    const summary: ComparisonEvidenceSummary = {
      comparisonId: "cmp-1",
      companyId: "c1",
      companyTicker: "ACT",
      companyName: "Acme",
      earlierPeriodEnd: "2023-06-30",
      laterPeriodEnd: "2024-06-30",
      gapMonths: 12,
      reportSideQuality: "GOOD",
      reportSideQualityLabel: "Analysis ready",
      alignmentChangeQuality: "USABLE",
      alignmentChangeQualityLabel: "Usable attribution",
      counts: { NEW: 3, REMOVED: 2, UNCHANGED: 1, LIGHTLY_MODIFIED: 1, SUBSTANTIALLY_MODIFIED: 1, AMBIGUOUS: 1 },
      totalCount: 9,
    };
    render(<ComparisonEvidenceSummarySection summary={summary} />);
    expect(screen.getByText("New")).toBeInTheDocument();
    expect(screen.getByText("Unchanged")).toBeInTheDocument();
    expect(screen.getByText("Total aligned passages")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });
});
