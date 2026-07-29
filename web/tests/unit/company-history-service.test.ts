import { describe, expect, it } from "vitest";
import {
  buildComparisonPreview,
  getCompanyHistoricalHighlights,
  getCompanyMetricSeries,
  resolveSelectedComparison,
} from "@/lib/services/company-history-service";
import { makeComparisonHistory, makeComparisonSummary } from "../fixtures/comparison-fixtures";

describe("getCompanyMetricSeries", () => {
  const history = makeComparisonHistory(3);

  it("extracts the disclosure_change value/label series by default (unit fallback)", () => {
    const series = getCompanyMetricSeries(history, undefined);
    expect(series).toHaveLength(3);
    expect(series[0].value).toBe(history[0].disclosureChangeScore);
  });

  it("extracts a different approved metric's series when selected", () => {
    const series = getCompanyMetricSeries(history, "uncertainty_change");
    expect(series[0].value).toBe(history[0].uncertaintyChange);
  });

  it("falls back to the default metric for an unapproved key", () => {
    const series = getCompanyMetricSeries(history, "not_a_real_metric");
    const defaultSeries = getCompanyMetricSeries(history, "disclosure_change");
    expect(series).toEqual(defaultSeries);
  });

  it("preserves a null value as a genuine gap, never coercing to 0", () => {
    const withGap = [makeComparisonSummary({ id: "cmp-gap", disclosureChangeScore: null, disclosureChangeLabel: null })];
    const series = getCompanyMetricSeries(withGap, "disclosure_change");
    expect(series[0].value).toBeNull();
  });

  it("carries irregular-gap/transition/historical-peak flags through to each point", () => {
    const flagged = [makeComparisonSummary({ isIrregularGap: true, isTransition: true, isHistoricalPeakChange: true })];
    const series = getCompanyMetricSeries(flagged, "disclosure_change");
    expect(series[0].isIrregularGap).toBe(true);
    expect(series[0].isTransition).toBe(true);
    expect(series[0].isHistoricalPeakChange).toBe(true);
  });

  it("handles an empty comparison list", () => {
    expect(getCompanyMetricSeries([], "disclosure_change")).toEqual([]);
  });

  it("handles a single-comparison history", () => {
    const single = makeComparisonHistory(1);
    expect(getCompanyMetricSeries(single, "disclosure_change")).toHaveLength(1);
  });
});

describe("getCompanyHistoricalHighlights", () => {
  it("finds the latest and historical-peak comparisons", () => {
    const history = makeComparisonHistory(3);
    history[1] = { ...history[1], isHistoricalPeakChange: true };
    const highlights = getCompanyHistoricalHighlights(history);
    expect(highlights.latestComparisonId).toBe(history[2].id);
    expect(highlights.historicalPeakChangeComparisonId).toBe(history[1].id);
  });

  it("only surfaces a primary-eligible uncertainty increase, never a review-qualified one", () => {
    const history = [
      makeComparisonSummary({ id: "a", reportSidePrimaryEligible: false, uncertaintyChange: 5 }),
      makeComparisonSummary({ id: "b", reportSidePrimaryEligible: true, uncertaintyChange: 2 }),
    ];
    const highlights = getCompanyHistoricalHighlights(history);
    expect(highlights.largestEligibleUncertaintyIncreaseComparisonId).toBe("b");
  });

  it("picks the largest eligible value among multiple eligible candidates", () => {
    const history = [
      makeComparisonSummary({ id: "a", alignmentChangePrimaryEligible: true, riskIntroductionRate: 1 }),
      makeComparisonSummary({ id: "b", alignmentChangePrimaryEligible: true, riskIntroductionRate: 5 }),
    ];
    const highlights = getCompanyHistoricalHighlights(history);
    expect(highlights.largestEligibleRiskIntroductionComparisonId).toBe("b");
  });

  it("returns null shortcuts when no comparison qualifies", () => {
    const history = [makeComparisonSummary({ reportSidePrimaryEligible: false, alignmentChangePrimaryEligible: false })];
    const highlights = getCompanyHistoricalHighlights(history);
    expect(highlights.largestEligibleUncertaintyIncreaseComparisonId).toBeNull();
    expect(highlights.largestEligibleRiskIntroductionComparisonId).toBeNull();
  });

  it("handles an empty history without throwing", () => {
    const highlights = getCompanyHistoricalHighlights([]);
    expect(highlights.latestComparisonId).toBeNull();
    expect(highlights.historicalPeakChangeComparisonId).toBeNull();
  });
});

describe("resolveSelectedComparison", () => {
  const history = makeComparisonHistory(3);

  it("selects the requested comparison when the id is valid", () => {
    expect(resolveSelectedComparison(history, history[0].id)?.id).toBe(history[0].id);
  });

  it("selects the latest comparison when no id is given", () => {
    expect(resolveSelectedComparison(history, null)?.id).toBe(history[2].id);
    expect(resolveSelectedComparison(history, undefined)?.id).toBe(history[2].id);
  });

  it("falls back safely to the latest comparison for an invalid/unknown id -- never throws", () => {
    expect(resolveSelectedComparison(history, "not-a-real-id")?.id).toBe(history[2].id);
  });

  it("returns null only when the company has zero comparisons", () => {
    expect(resolveSelectedComparison([], "anything")).toBeNull();
  });
});

describe("buildComparisonPreview", () => {
  it("assembles findings and six headline metrics for a comparison", () => {
    const comparison = makeComparisonSummary();
    const preview = buildComparisonPreview(comparison);
    expect(preview.comparison.id).toBe(comparison.id);
    expect(preview.headlineMetrics).toHaveLength(6);
    expect(preview.findings.length).toBeGreaterThan(0);
  });
});
