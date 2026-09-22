/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscoveryResultsTable } from "@/components/DiscoveryResultsTable";
import type { DiscoveryItem } from "@/lib/domain/discovery";

function makeItem(overrides: Partial<DiscoveryItem> = {}): DiscoveryItem {
  return {
    id: "d1",
    discoveryType: "largest_risk_introduction",
    rankScope: "corpus",
    rank: 1,
    percentile: 90,
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    reportComparisonId: "cmp-1",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    findingHeadline: "Risk language introduced",
    supportingValue: 2.1,
    supportingValueDisplay: "+2.10 / 1,000 words",
    supportingUnit: "rate_per_1000_words",
    qualityLabel: "Strong attribution",
    ...overrides,
  };
}

describe("DiscoveryResultsTable", () => {
  it("renders rows in the given (already-deterministic) order, unmodified", () => {
    render(<DiscoveryResultsTable items={[makeItem({ rank: 1, id: "a" }), makeItem({ rank: 2, id: "b", companyTicker: "BEL", companyName: "Bellwether" })]} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0].textContent).toContain("Acme Corp");
    expect(rows[1].textContent).toContain("Bellwether");
  });

  it("links each row to its comparison detail page", () => {
    render(<DiscoveryResultsTable items={[makeItem()]} />);
    expect(screen.getByRole("link", { name: /View comparison/ })).toHaveAttribute("href", "/comparisons/cmp-1");
  });

  it("renders a restrained empty state for no results", () => {
    render(<DiscoveryResultsTable items={[]} />);
    expect(screen.getByText(/No results for these filters/)).toBeInTheDocument();
  });

  it("Track 7F.4 item 8: renders a distinct no-comparisons state, not the generic empty state", () => {
    render(<DiscoveryResultsTable items={[]} financialConditionCompanyStatus={{ status: "no_comparisons" }} />);
    expect(screen.getByText(/No comparisons available for this company/)).toBeInTheDocument();
    expect(screen.queryByText(/No results for these filters/)).not.toBeInTheDocument();
  });

  it("Track 7F.4 item 8: renders a distinct failed-quality state", () => {
    render(<DiscoveryResultsTable items={[]} financialConditionCompanyStatus={{ status: "failed_quality" }} />);
    expect(screen.getByText(/didn't clear the quality gate/)).toBeInTheDocument();
  });

  it("Track 7F.4 item 8: renders a distinct below-materiality state with the observed value and threshold, never as an eligible finding", () => {
    render(
      <DiscoveryResultsTable
        items={[]}
        financialConditionCompanyStatus={{
          status: "below_materiality",
          observedValue: 0.021,
          threshold: 0.04,
          reportComparisonId: "cmp-below",
          earlierPeriodEnd: "2023-06-30",
          laterPeriodEnd: "2024-06-30",
        }}
      />,
    );
    expect(screen.getByText(/Below materiality threshold/)).toBeInTheDocument();
    expect(screen.getByText(/2\.1%/)).toBeInTheDocument();
    expect(screen.getByText(/4\.0%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View this comparison/ })).toHaveAttribute("href", "/comparisons/cmp-below");
  });
});
