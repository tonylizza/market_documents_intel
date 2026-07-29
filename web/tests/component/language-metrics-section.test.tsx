/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LanguageMetricsSection } from "@/components/LanguageMetricsSection";
import type { LanguageMetric } from "@/lib/domain/comparison";

function makeMetric(overrides: Partial<LanguageMetric> = {}): LanguageMetric {
  return {
    id: "m1",
    scope: "report_side",
    population: "primary_narrative",
    category: "positive",
    subcategory: null,
    earlierRatePer1000: 5,
    laterRatePer1000: 6.5,
    rateChange: 1.5,
    absoluteRateChange: 1.5,
    introducedRatePer1000: null,
    removedRatePer1000: null,
    retainedCount: null,
    quality: "GOOD",
    primaryEligible: true,
    ...overrides,
  };
}

describe("LanguageMetricsSection -- report-side variant", () => {
  it("renders the same categories in the table as in the chart-backing data", () => {
    render(<LanguageMetricsSection metrics={[makeMetric({ category: "positive" }), makeMetric({ id: "m2", category: "negative" })]} variant="report-side" />);
    expect(screen.getByText("Positive")).toBeInTheDocument();
    expect(screen.getByText("Negative")).toBeInTheDocument();
  });

  it("shows earlier rate, later rate, and change columns", () => {
    render(<LanguageMetricsSection metrics={[makeMetric()]} variant="report-side" />);
    expect(screen.getByRole("columnheader", { name: /Earlier rate/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Later rate/ })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /Change/ })).toBeInTheDocument();
  });

  it("sorting by category toggles descending/ascending order", async () => {
    const user = userEvent.setup();
    render(
      <LanguageMetricsSection
        metrics={[makeMetric({ id: "m1", category: "negative" }), makeMetric({ id: "m2", category: "positive" })]}
        variant="report-side"
      />,
    );
    // Selecting a new sort column defaults to descending.
    await user.click(screen.getByRole("button", { name: /Category/ }));
    const rowsDesc = screen.getAllByRole("row").slice(1).map((row) => row.textContent);
    expect(rowsDesc[0]).toContain("Positive");
    // Clicking the same column again toggles to ascending.
    await user.click(screen.getByRole("button", { name: /Category/ }));
    const rowsAsc = screen.getAllByRole("row").slice(1).map((row) => row.textContent);
    expect(rowsAsc[0]).toContain("Negative");
  });

  it("renders an empty state for zero metrics", () => {
    render(<LanguageMetricsSection metrics={[]} variant="report-side" />);
    expect(screen.getByText(/No language metrics available/)).toBeInTheDocument();
  });
});

describe("LanguageMetricsSection -- alignment-change variant", () => {
  it("shows introduced/removed/retained columns instead of earlier/later", () => {
    render(
      <LanguageMetricsSection
        metrics={[makeMetric({ scope: "alignment_change", introducedRatePer1000: 3, removedRatePer1000: 1, retainedCount: 5 })]}
        variant="alignment-change"
      />,
    );
    expect(screen.getByRole("columnheader", { name: "Introduced" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Removed" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Retained" })).toBeInTheDocument();
  });
});
