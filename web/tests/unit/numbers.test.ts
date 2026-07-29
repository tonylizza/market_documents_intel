import { describe, expect, it } from "vitest";
import { formatCount, formatMetricValue, formatPercentile } from "@/lib/formatting/numbers";

describe("formatCount", () => {
  it("formats with thousands separators", () => {
    expect(formatCount(22169)).toBe("22,169");
  });

  it("formats small numbers plainly", () => {
    expect(formatCount(6)).toBe("6");
  });
});

describe("formatPercentile", () => {
  it("formats a rounded percentile", () => {
    expect(formatPercentile(79.6)).toBe("80th percentile");
  });

  it("returns null for null", () => {
    expect(formatPercentile(null)).toBeNull();
  });
});

describe("formatMetricValue", () => {
  it("formats score_0_1 to two decimals", () => {
    expect(formatMetricValue(0.5876890246289987, "score_0_1")).toBe("0.59");
  });

  it("formats share as a percentage", () => {
    expect(formatMetricValue(0.123, "share")).toBe("12.3%");
  });

  it("formats rate_per_1000_words with an explicit sign and unit", () => {
    expect(formatMetricValue(1.5, "rate_per_1000_words")).toBe("+1.50 / 1,000 words");
    expect(formatMetricValue(-1.5, "rate_per_1000_words")).toBe("-1.50 / 1,000 words");
  });

  it("falls back to a plain number for an unrecognized unit", () => {
    expect(formatMetricValue(42, "widgets")).toBe("42");
  });

  it("returns null for a null value, never a fabricated zero", () => {
    expect(formatMetricValue(null, "score_0_1")).toBeNull();
  });
});
