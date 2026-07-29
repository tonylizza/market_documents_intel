/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AdaptiveComparisonNavigator } from "@/components/AdaptiveComparisonNavigator";
import { makeComparisonHistory } from "../fixtures/comparison-fixtures";
import type { CompanyHistoricalHighlights } from "@/lib/domain/company";

const EMPTY_HIGHLIGHTS: CompanyHistoricalHighlights = {
  latestComparisonId: null,
  historicalPeakChangeComparisonId: null,
  largestEligibleUncertaintyIncreaseComparisonId: null,
  largestEligibleRiskIntroductionComparisonId: null,
};

function renderNavigator(count: number, highlights: CompanyHistoricalHighlights = EMPTY_HIGHLIGHTS) {
  const comparisons = makeComparisonHistory(count);
  render(
    <AdaptiveComparisonNavigator
      comparisons={comparisons}
      companyTicker="ACT"
      selectedComparisonId={comparisons[comparisons.length - 1]?.id ?? null}
      highlights={highlights}
    />,
  );
  return comparisons;
}

describe("AdaptiveComparisonNavigator -- mode selection by comparison count", () => {
  it("renders an empty message for zero comparisons", () => {
    renderNavigator(0);
    expect(screen.getByText(/No comparisons are available/)).toBeInTheDocument();
  });

  it("uses compact mode for 1 comparison", () => {
    renderNavigator(1);
    expect(screen.getByTestId("navigator-compact")).toBeInTheDocument();
  });

  it("uses compact mode for 5 comparisons", () => {
    renderNavigator(5);
    expect(screen.getByTestId("navigator-compact")).toBeInTheDocument();
  });

  it("uses compact mode at exactly the compact threshold (10)", () => {
    renderNavigator(10);
    expect(screen.getByTestId("navigator-compact")).toBeInTheDocument();
  });

  it("uses scrollable mode just above the compact threshold (11)", () => {
    renderNavigator(11);
    expect(screen.getByTestId("navigator-scrollable")).toBeInTheDocument();
  });

  it("uses scrollable mode at exactly the scrollable threshold (20)", () => {
    renderNavigator(20);
    expect(screen.getByTestId("navigator-scrollable")).toBeInTheDocument();
  });

  it("uses range-filtered mode just above the scrollable threshold (21)", () => {
    renderNavigator(21);
    expect(screen.getByTestId("navigator-range-filtered")).toBeInTheDocument();
  });

  it("uses range-filtered mode for a long history (35)", () => {
    renderNavigator(35);
    expect(screen.getByTestId("navigator-range-filtered")).toBeInTheDocument();
  });
});

describe("AdaptiveComparisonNavigator -- scrollable mode controls", () => {
  it("renders previous/next controls and a range indicator", () => {
    renderNavigator(15);
    expect(screen.getByRole("button", { name: /Scroll to earlier/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Scroll to later/i })).toBeInTheDocument();
    expect(screen.getByText(/of 15 comparisons/)).toBeInTheDocument();
  });

  it("the selected card is rendered with aria-current inside the scrollable strip", () => {
    const comparisons = renderNavigator(15);
    const selected = comparisons[comparisons.length - 1];
    const links = screen.getAllByRole("link");
    const current = links.find((link) => link.getAttribute("aria-current") === "true");
    expect(current).toHaveAttribute("href", `/companies/ACT?comparison=${selected.id}`);
  });
});

describe("AdaptiveComparisonNavigator -- range-filtered mode", () => {
  it("defaults to showing the latest window (10) of a long history", () => {
    renderNavigator(35);
    expect(screen.getByText(/Showing 10 of 35 comparisons/)).toBeInTheDocument();
  });

  it("switching to 'All' shows the full history", () => {
    renderNavigator(35);
    fireEvent.click(screen.getByRole("button", { name: /All 35/ }));
    expect(screen.getByText(/Showing 35 of 35 comparisons/)).toBeInTheDocument();
  });

  it("renders only the shortcuts that have a real comparison id", () => {
    renderNavigator(35, {
      ...EMPTY_HIGHLIGHTS,
      latestComparisonId: "cmp-34",
      historicalPeakChangeComparisonId: null,
    });
    expect(screen.getByRole("link", { name: "Latest comparison" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Historical peak change" })).not.toBeInTheDocument();
  });
});
