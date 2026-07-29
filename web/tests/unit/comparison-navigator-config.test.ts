import { describe, expect, it } from "vitest";
import {
  COMPARISON_METRIC_KEYS,
  DEFAULT_COMPARISON_METRIC,
  NAVIGATOR_THRESHOLDS,
  isApprovedComparisonMetricKey,
  resolveComparisonMetricKey,
  selectNavigatorMode,
} from "@/lib/config/comparison";

describe("selectNavigatorMode", () => {
  it("returns compact at and below the compact threshold", () => {
    expect(selectNavigatorMode(1)).toBe("compact");
    expect(selectNavigatorMode(NAVIGATOR_THRESHOLDS.compactMax)).toBe("compact");
  });

  it("returns scrollable just above the compact threshold (compact/scrollable boundary)", () => {
    expect(selectNavigatorMode(NAVIGATOR_THRESHOLDS.compactMax + 1)).toBe("scrollable");
  });

  it("returns scrollable at the scrollable threshold", () => {
    expect(selectNavigatorMode(NAVIGATOR_THRESHOLDS.scrollableMax)).toBe("scrollable");
  });

  it("returns range-filtered just above the scrollable threshold (scrollable/range-filtered boundary)", () => {
    expect(selectNavigatorMode(NAVIGATOR_THRESHOLDS.scrollableMax + 1)).toBe("range-filtered");
  });

  it("returns range-filtered for a large history", () => {
    expect(selectNavigatorMode(35)).toBe("range-filtered");
  });

  it("returns compact for zero comparisons", () => {
    expect(selectNavigatorMode(0)).toBe("compact");
  });
});

describe("isApprovedComparisonMetricKey / resolveComparisonMetricKey", () => {
  it("accepts every approved key", () => {
    for (const key of COMPARISON_METRIC_KEYS) {
      expect(isApprovedComparisonMetricKey(key)).toBe(true);
      expect(resolveComparisonMetricKey(key)).toBe(key);
    }
  });

  it("rejects an unapproved/arbitrary metric key", () => {
    expect(isApprovedComparisonMetricKey("some_arbitrary_metric")).toBe(false);
  });

  it("falls back to the default metric for an invalid value", () => {
    expect(resolveComparisonMetricKey("not_a_real_metric")).toBe(DEFAULT_COMPARISON_METRIC);
  });

  it("falls back to the default metric for a missing value", () => {
    expect(resolveComparisonMetricKey(null)).toBe(DEFAULT_COMPARISON_METRIC);
    expect(resolveComparisonMetricKey(undefined)).toBe(DEFAULT_COMPARISON_METRIC);
  });
});
