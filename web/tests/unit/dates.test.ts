import { describe, expect, it } from "vitest";
import { formatComparisonPeriod, formatPeriodEnd, formatReportRange, formatYear } from "@/lib/formatting/dates";

describe("formatPeriodEnd", () => {
  it("formats an ISO date string as 'D Mon YYYY'", () => {
    expect(formatPeriodEnd("2024-06-30")).toBe("30 Jun 2024");
  });

  it("never shifts the date via timezone conversion", () => {
    // A naive `new Date("2024-06-30")` interpreted as UTC and then rendered
    // in a negative-UTC-offset timezone would show 29 June -- this must not
    // happen since we never construct a `Date` object at all.
    expect(formatPeriodEnd("2024-01-01")).toBe("1 Jan 2024");
    expect(formatPeriodEnd("2024-12-31")).toBe("31 Dec 2024");
  });

  it("returns null for a null value", () => {
    expect(formatPeriodEnd(null)).toBeNull();
  });

  it("returns null for an unparseable string", () => {
    expect(formatPeriodEnd("not-a-date")).toBeNull();
  });
});

describe("formatYear", () => {
  it("extracts the year", () => {
    expect(formatYear("2019-12-31")).toBe("2019");
  });

  it("returns null for null", () => {
    expect(formatYear(null)).toBeNull();
  });
});

describe("formatReportRange", () => {
  it("formats a multi-year range", () => {
    expect(formatReportRange("2016-06-30", "2024-06-30")).toBe("2016 – 2024");
  });

  it("formats a single year when first and last are the same year", () => {
    expect(formatReportRange("2024-06-30", "2024-12-31")).toBe("2024");
  });

  it("returns null when both are null", () => {
    expect(formatReportRange(null, null)).toBeNull();
  });

  it("falls back to whichever single value is present", () => {
    expect(formatReportRange("2016-06-30", null)).toBe("2016");
    expect(formatReportRange(null, "2024-06-30")).toBe("2024");
  });
});

describe("formatComparisonPeriod", () => {
  it("formats an earlier-to-later arrow string", () => {
    expect(formatComparisonPeriod("2023-06-30", "2024-06-30")).toBe("30 Jun 2023 → 30 Jun 2024");
  });

  it("returns null when both are null", () => {
    expect(formatComparisonPeriod(null, null)).toBeNull();
  });

  it("falls back to whichever single value is present", () => {
    expect(formatComparisonPeriod("2023-06-30", null)).toBe("30 Jun 2023");
    expect(formatComparisonPeriod(null, "2024-06-30")).toBe("30 Jun 2024");
  });

  it("duplicate nominal-year formatting: two comparisons landing in the same calendar year still show unambiguous full dates, never bare year", () => {
    // Two different comparisons for two companies with reports six months
    // apart both fall in 2024 -- formatComparisonPeriod always renders full
    // day/month/year (never just the year), so the two remain distinguishable
    // without any special-cased "duplicate year" branch.
    const first = formatComparisonPeriod("2023-01-31", "2024-01-31");
    const second = formatComparisonPeriod("2023-06-30", "2024-06-30");
    expect(first).toBe("31 Jan 2023 → 31 Jan 2024");
    expect(second).toBe("30 Jun 2023 → 30 Jun 2024");
    expect(first).not.toBe(second);
  });

  it("irregular-gap display: a non-12-month gap is still rendered as exact dates, not an assumed annual cadence", () => {
    // gap_months is a separate published field (see ComparisonSummary.gapMonths) --
    // formatComparisonPeriod itself never assumes or computes a gap length,
    // it only ever renders the two real dates it was given.
    expect(formatComparisonPeriod("2022-03-31", "2024-09-30")).toBe("31 Mar 2022 → 30 Sep 2024");
  });
});
