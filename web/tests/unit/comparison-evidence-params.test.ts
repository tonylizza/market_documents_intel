import { describe, expect, it } from "vitest";
import {
  buildComparisonEvidenceQueryString,
  parseComparisonEvidenceFilters,
  resetEvidencePage,
} from "@/lib/services/comparison-evidence-params";

describe("parseComparisonEvidenceFilters", () => {
  it("defaults status to ALL", () => {
    expect(parseComparisonEvidenceFilters({}).status).toBe("ALL");
  });

  it("validates status against the controlled vocabulary", () => {
    expect(parseComparisonEvidenceFilters({ status: "NEW" }).status).toBe("NEW");
    expect(parseComparisonEvidenceFilters({ status: "not-real" }).status).toBe("ALL");
  });

  it("normalizes page/pageSize", () => {
    expect(parseComparisonEvidenceFilters({ page: "0" }).page).toBe(1);
    expect(parseComparisonEvidenceFilters({ page: "3" }).page).toBe(3);
  });

  it("only accepts subcategory alongside category", () => {
    expect(parseComparisonEvidenceFilters({ subcategory: "climate_environmental" }).subcategory).toBeNull();
    expect(parseComparisonEvidenceFilters({ category: "risk", subcategory: "climate_environmental" }).subcategory).toBe(
      "climate_environmental",
    );
  });

  it("parses tri-state flags and page range", () => {
    const filters = parseComparisonEvidenceFilters({ collision: "1", heading: "0", pageStart: "5", pageEnd: "10" });
    expect(filters.collisionFlag).toBe(true);
    expect(filters.hasHeading).toBe(false);
    expect(filters.pageStart).toBe(5);
    expect(filters.pageEnd).toBe(10);
  });
});

describe("buildComparisonEvidenceQueryString round-trip", () => {
  it("round-trips every field and omits defaults", () => {
    const original = parseComparisonEvidenceFilters({ status: "NEW", confidence: "HIGH", collision: "1", page: "2" });
    const serialized = buildComparisonEvidenceQueryString(original);
    const roundTripped = parseComparisonEvidenceFilters(Object.fromEntries(new URLSearchParams(serialized)));
    expect(roundTripped).toEqual(original);
  });

  it("produces an empty string for all-default filters", () => {
    expect(buildComparisonEvidenceQueryString(parseComparisonEvidenceFilters({}))).toBe("");
  });
});

describe("resetEvidencePage", () => {
  it("resets page to 1", () => {
    const filters = parseComparisonEvidenceFilters({ status: "NEW", page: "4" });
    expect(resetEvidencePage(filters).page).toBe(1);
    expect(resetEvidencePage(filters).status).toBe("NEW");
  });
});
