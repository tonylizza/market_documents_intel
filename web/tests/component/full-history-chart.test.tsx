/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FullHistoryChart } from "@/components/FullHistoryChart";
import { COMPARISON_METRICS } from "@/lib/config/comparison";
import type { CompanyMetricPoint } from "@/lib/domain/company";

const METRIC = COMPARISON_METRICS.disclosure_change;

function makePoint(overrides: Partial<CompanyMetricPoint> = {}): CompanyMetricPoint {
  return {
    comparisonId: "cmp-1",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    value: 0.4,
    label: "Moderate change",
    isIrregularGap: false,
    isTransition: false,
    isHistoricalPeakChange: false,
    ...overrides,
  };
}

describe("FullHistoryChart -- empty state", () => {
  it("renders an empty state for zero points", () => {
    render(<FullHistoryChart points={[]} metric={METRIC} />);
    expect(screen.getByText(/No comparison history available/)).toBeInTheDocument();
  });

  it("renders a not-available note when every point has a null value", () => {
    render(<FullHistoryChart points={[makePoint({ value: null, label: null })]} metric={METRIC} />);
    expect(screen.getByText(/is not available/)).toBeInTheDocument();
  });
});

describe("FullHistoryChart -- data summary and table alternative", () => {
  it("provides an accessible text summary of the chart", () => {
    render(<FullHistoryChart points={[makePoint()]} metric={METRIC} />);
    expect(screen.getByText(/Line chart of Disclosure change/)).toBeInTheDocument();
  });

  it("renders a data table with the same points as the chart, behind a disclosure toggle", () => {
    render(<FullHistoryChart points={[makePoint(), makePoint({ comparisonId: "cmp-2", laterPeriodEnd: "2022-06-30" })]} metric={METRIC} />);
    const table = screen.getByRole("table", { hidden: true });
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
  });

  it("handles a single-point series without throwing", () => {
    render(<FullHistoryChart points={[makePoint()]} metric={METRIC} />);
    expect(screen.getByText(/across 1 comparison,/)).toBeInTheDocument();
  });

  it("flags an irregular-gap comparison in the table", () => {
    render(<FullHistoryChart points={[makePoint({ isIrregularGap: true })]} metric={METRIC} />);
    const table = screen.getByRole("table", { hidden: true });
    expect(table.textContent).toContain("Irregular gap");
  });
});
