/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HeadlineMetricCard } from "@/components/HeadlineMetricCard";
import type { HeadlineMetric } from "@/lib/domain/comparison";

function makeMetric(overrides: Partial<HeadlineMetric> = {}): HeadlineMetric {
  return {
    metricKey: "disclosure_change",
    displayName: "Overall disclosure change",
    value: 0.42,
    valueDisplay: "Moderate change",
    unit: "score_0_1",
    quality: "NEEDS_REVIEW",
    qualityLabel: "Review recommended",
    qualityDimension: "disclosure-change",
    primaryEligible: false,
    explanation: "How much this report's disclosures changed overall.",
    reviewQualifiedExploratory: true,
    ...overrides,
  };
}

describe("HeadlineMetricCard", () => {
  it("renders the display name, value, and explanation", () => {
    render(<HeadlineMetricCard metric={makeMetric()} />);
    expect(screen.getByRole("heading", { name: "Overall disclosure change" })).toBeInTheDocument();
    expect(screen.getByText("Moderate change")).toBeInTheDocument();
    expect(screen.getByText(/How much this report's disclosures changed/)).toBeInTheDocument();
  });

  it("shows the exploratory note only when reviewQualifiedExploratory is true", () => {
    render(<HeadlineMetricCard metric={makeMetric({ reviewQualifiedExploratory: true })} />);
    expect(screen.getByText(/excluded from primary discovery rankings/)).toBeInTheDocument();
  });

  it("does not show the exploratory note for a non-exploratory metric", () => {
    render(<HeadlineMetricCard metric={makeMetric({ reviewQualifiedExploratory: false, metricKey: "net_tone_change" })} />);
    expect(screen.queryByText(/excluded from primary discovery rankings/)).not.toBeInTheDocument();
  });

  it("renders 'Not available' for a null value rather than a blank or zero", () => {
    render(<HeadlineMetricCard metric={makeMetric({ value: null, valueDisplay: null })} />);
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
  });

  it("technical details are collapsed by default", () => {
    render(<HeadlineMetricCard metric={makeMetric()} />);
    const details = screen.getByText("Technical details").closest("details");
    expect(details).not.toHaveAttribute("open");
  });
});
