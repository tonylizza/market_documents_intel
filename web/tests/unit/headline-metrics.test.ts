import { describe, expect, it } from "vitest";
import { HEADLINE_METRIC_KEYS, buildHeadlineMetrics } from "@/lib/services/headline-metrics";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

describe("buildHeadlineMetrics", () => {
  it("builds exactly the six fixed headline metrics, in order", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary());
    expect(metrics).toHaveLength(6);
    expect(metrics.map((m) => m.metricKey)).toEqual([...HEADLINE_METRIC_KEYS]);
  });

  it("never includes risk_removal (full-history-chart-only, not a headline card)", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary());
    expect(metrics.some((m) => m.metricKey === "risk_removal")).toBe(false);
  });

  it("marks disclosure_change as review-qualified-exploratory when not primary eligible", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary({ disclosureChangePrimaryEligible: false }));
    const disclosureChange = metrics.find((m) => m.metricKey === "disclosure_change");
    expect(disclosureChange?.reviewQualifiedExploratory).toBe(true);
  });

  it("does not mark disclosure_change as exploratory when it is primary eligible", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary({ disclosureChangePrimaryEligible: true }));
    const disclosureChange = metrics.find((m) => m.metricKey === "disclosure_change");
    expect(disclosureChange?.reviewQualifiedExploratory).toBe(false);
  });

  it("never marks a non-disclosure-change metric as exploratory", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary());
    const others = metrics.filter((m) => m.metricKey !== "disclosure_change");
    expect(others.every((m) => m.reviewQualifiedExploratory === false)).toBe(true);
  });

  it("assigns the correct quality dimension per metric -- report-side, alignment-change, and disclosure-change are never mixed up", () => {
    const metrics = buildHeadlineMetrics(makeComparisonSummary());
    const byKey = Object.fromEntries(metrics.map((m) => [m.metricKey, m]));
    expect(byKey.disclosure_change.qualityDimension).toBe("disclosure-change");
    expect(byKey.risk_introduction.qualityDimension).toBe("alignment-change");
    expect(byKey.net_tone_change.qualityDimension).toBe("report-side");
    expect(byKey.governance_change.qualityDimension).toBe("report-side");
  });

  it("renders a null value with a null valueDisplay fallback rather than throwing", () => {
    const metrics = buildHeadlineMetrics(
      makeComparisonSummary({ netToneChange: null, netToneChangeLabel: null }),
    );
    const netTone = metrics.find((m) => m.metricKey === "net_tone_change");
    expect(netTone?.value).toBeNull();
  });
});
