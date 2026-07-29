/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonEvidenceStatusTabs } from "@/components/ComparisonEvidenceStatusTabs";
import { parseComparisonEvidenceFilters } from "@/lib/services/comparison-evidence-params";
import type { ComparisonEvidenceSummary } from "@/lib/domain/passage";

function makeSummary(): ComparisonEvidenceSummary {
  return {
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
    counts: { NEW: 1, REMOVED: 1, UNCHANGED: 1, LIGHTLY_MODIFIED: 1, SUBSTANTIALLY_MODIFIED: 1, AMBIGUOUS: 1 },
    totalCount: 6,
  };
}

describe("ComparisonEvidenceStatusTabs", () => {
  it("renders All plus all 6 alignment-status tabs as real links", () => {
    render(<ComparisonEvidenceStatusTabs comparisonId="cmp-1" filters={parseComparisonEvidenceFilters({})} summary={makeSummary()} />);
    for (const label of ["All", "New", "Removed", "Unchanged", "Lightly modified", "Substantially modified", "Ambiguous"]) {
      expect(screen.getByRole("link", { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
  });

  it("marks the active tab with aria-current", () => {
    render(<ComparisonEvidenceStatusTabs comparisonId="cmp-1" filters={parseComparisonEvidenceFilters({ status: "NEW" })} summary={makeSummary()} />);
    expect(screen.getByRole("link", { name: /^New/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /^All/ })).not.toHaveAttribute("aria-current");
  });

  it("preserves other filters and resets the page when switching tabs", () => {
    render(
      <ComparisonEvidenceStatusTabs
        comparisonId="cmp-1"
        filters={parseComparisonEvidenceFilters({ status: "ALL", confidence: "HIGH", page: "3" })}
        summary={makeSummary()}
      />,
    );
    const href = screen.getByRole("link", { name: /^New/ }).getAttribute("href")!;
    expect(href).toContain("status=NEW");
    expect(href).toContain("confidence=HIGH");
    expect(href).not.toContain("page=");
  });

  it("every tab link is keyboard-focusable (ordinary anchor, no positive tabindex trickery)", () => {
    render(<ComparisonEvidenceStatusTabs comparisonId="cmp-1" filters={parseComparisonEvidenceFilters({})} summary={makeSummary()} />);
    for (const link of screen.getAllByRole("link")) {
      expect(link.tabIndex).not.toBeGreaterThan(0);
    }
  });
});
