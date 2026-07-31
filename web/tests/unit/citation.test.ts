import { describe, expect, it } from "vitest";
import { formatCitationLabel } from "@/lib/services/citation";
import type { RetrievalContext } from "@/lib/domain/retrieval";

function baseContext(overrides: Partial<RetrievalContext> = {}): RetrievalContext {
  return {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED",
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "KP2",
    companyName: "Kappa Two",
    reportSide: "LATER",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    reportPeriodEnd: "2024-06-30",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    heading: "Liquidity",
    passageType: "PARAGRAPH",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    reportSideQuality: "GOOD",
    alignmentChangeQuality: "GOOD",
    collisionFlag: false,
    splitMergeFlag: false,
    irregularGapFlag: false,
    firstPageNumber: 43,
    lastPageNumber: 44,
    wordCount: 120,
    text: "The group maintains adequate liquidity headroom.",
    categories: [],
    riskSubcategories: [],
    ...overrides,
  };
}

describe("formatCitationLabel", () => {
  it("formats a comparison-linked later-side citation with a page range", () => {
    const label = formatCitationLabel(baseContext());
    expect(label).toBe("KP2, 2023->2024 comparison, later report, pp. 43-44");
  });

  it("formats a comparison-linked earlier-side citation", () => {
    const label = formatCitationLabel(baseContext({ reportSide: "EARLIER" }));
    expect(label).toBe("KP2, 2023->2024 comparison, earlier report, pp. 43-44");
  });

  it("formats a single page without a range", () => {
    const label = formatCitationLabel(baseContext({ firstPageNumber: 18, lastPageNumber: 18 }));
    expect(label).toContain("p. 18");
    expect(label).not.toContain("pp.");
  });

  it("formats a REPORT_ONLY citation without comparison periods", () => {
    const label = formatCitationLabel(
      baseContext({
        contextType: "REPORT_ONLY",
        passageComparisonId: null,
        reportComparisonId: null,
        reportSide: null,
        alignmentStatus: null,
        alignmentType: null,
        confidence: null,
        earlierPeriodEnd: null,
        laterPeriodEnd: null,
        reportPeriodEnd: "2021-06-30",
        firstPageNumber: 18,
        lastPageNumber: 18,
        companyTicker: "ACT",
      }),
    );
    expect(label).toBe("ACT, 2021 report, p. 18");
  });

  it("never includes raw vector or similarity data", () => {
    const label = formatCitationLabel(baseContext());
    expect(label).not.toMatch(/\d\.\d{3,}/);
  });
});
