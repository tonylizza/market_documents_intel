/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ComparisonNavigatorCard } from "@/components/ComparisonNavigatorCard";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

describe("ComparisonNavigatorCard", () => {
  it("renders as a real link to the company page with the comparison id in the query string", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary({ id: "cmp-42" })} companyTicker="ACT" selected={false} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/companies/ACT?comparison=cmp-42");
  });

  it("marks the selected card with aria-current", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary()} companyTicker="ACT" selected={true} />);
    expect(screen.getByRole("link")).toHaveAttribute("aria-current", "true");
  });

  it("does not set aria-current when not selected", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary()} companyTicker="ACT" selected={false} />);
    expect(screen.getByRole("link")).not.toHaveAttribute("aria-current");
  });

  it("shows Review recommended directly on the card, never hidden in a technical section", () => {
    render(
      <ComparisonNavigatorCard
        comparison={makeComparisonSummary({ disclosureChangeQuality: "NEEDS_REVIEW", disclosureChangeQualityLabel: "Review recommended" })}
        companyTicker="ACT"
        selected={false}
      />,
    );
    expect(screen.getByText("Review recommended")).toBeInTheDocument();
  });

  it("shows the historical-peak flag when set", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary({ isHistoricalPeakChange: true })} companyTicker="ACT" selected={false} />);
    expect(screen.getByText("Historical peak change")).toBeInTheDocument();
  });

  it("shows an irregular-gap indicator when set", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary({ isIrregularGap: true, gapMonths: 18 })} companyTicker="ACT" selected={false} />);
    expect(screen.getByText(/Irregular reporting gap/)).toBeInTheDocument();
  });

  it("shows a transition-report indicator when set", () => {
    render(<ComparisonNavigatorCard comparison={makeComparisonSummary({ isTransition: true })} companyTicker="ACT" selected={false} />);
    expect(screen.getByText("Transition report")).toBeInTheDocument();
  });
});
