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
});
