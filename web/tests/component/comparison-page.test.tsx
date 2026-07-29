/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import type { LanguageMetric, PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

function makeDetail(): ReportComparisonDetail {
  return {
    ...makeComparisonSummary({ id: "cmp-1" }),
    companyTicker: "ACT",
    companyName: "Acme Corp",
    dictionaryMatchRateEarlier: 0.9,
    dictionaryMatchRateLater: 0.91,
    ambiguousWordShare: 0.02,
    collisionFlaggedWordShare: 0.01,
    unmatchedWordShare: 0.05,
    structuredContentExclusionShare: 0.1,
    reportSideWarning: null,
    alignmentChangeWarning: null,
  };
}

const LANGUAGE_METRICS: LanguageMetric[] = [
  {
    id: "m1",
    scope: "report_side",
    population: "primary_narrative",
    category: "positive",
    subcategory: null,
    earlierRatePer1000: 5,
    laterRatePer1000: 6.5,
    rateChange: 1.5,
    absoluteRateChange: 1.5,
    introducedRatePer1000: null,
    removedRatePer1000: null,
    retainedCount: null,
    quality: "GOOD",
    primaryEligible: true,
  },
  {
    id: "m2",
    scope: "alignment_change",
    population: "primary_narrative_excl_ambiguous",
    category: "risk",
    subcategory: null,
    earlierRatePer1000: null,
    laterRatePer1000: null,
    rateChange: null,
    absoluteRateChange: null,
    introducedRatePer1000: 3,
    removedRatePer1000: 1,
    retainedCount: 5,
    quality: "USABLE",
    primaryEligible: true,
  },
];

const COMPOSITION: PassageComposition = {
  comparisonId: "cmp-1",
  totalCount: 6,
  buckets: [
    { status: "NEW", count: 1, share: 1 / 6 },
    { status: "REMOVED", count: 1, share: 1 / 6 },
    { status: "SUBSTANTIALLY_MODIFIED", count: 1, share: 1 / 6 },
    { status: "LIGHTLY_MODIFIED", count: 1, share: 1 / 6 },
    { status: "UNCHANGED", count: 1, share: 1 / 6 },
    { status: "AMBIGUOUS", count: 1, share: 1 / 6 },
  ],
  qualityNote: "Composition reflects passage-level alignment status.",
};

let mockDetail: ReportComparisonDetail | null = makeDetail();
let mockShouldThrow = false;

vi.mock("@/lib/repositories/postgres-comparison-repository", () => ({
  PostgresComparisonRepository: class {
    async getComparisonById() {
      if (mockShouldThrow) throw new Error("connection refused");
      return mockDetail;
    }
    async getComparisonLanguageMetrics() {
      return LANGUAGE_METRICS;
    }
    async getComparisonPassageComposition() {
      return COMPOSITION;
    }
  },
}));

const { default: ComparisonPage } = await import("@/app/comparisons/[comparisonId]/page");

describe("ComparisonPage", () => {
  it("renders the header, three distinct quality dimensions, and six headline metrics", async () => {
    mockDetail = makeDetail();
    mockShouldThrow = false;
    const jsx = await ComparisonPage({ params: Promise.resolve({ comparisonId: "cmp-1" }) });
    render(jsx);
    expect(screen.getByText("Acme Corp (ACT)")).toBeInTheDocument();
    const qualitySummary = within(screen.getByRole("region", { name: "Quality summary" }));
    expect(qualitySummary.getByRole("status", { name: "Report-side quality: Analysis ready" })).toBeInTheDocument();
    expect(qualitySummary.getByRole("status", { name: "Alignment-change quality: Usable attribution" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { name: "Overall disclosure change" }).length).toBeGreaterThan(0);
  });

  it("always shows Review recommended for the review-qualified disclosure-change score", async () => {
    mockDetail = makeDetail();
    const jsx = await ComparisonPage({ params: Promise.resolve({ comparisonId: "cmp-1" }) });
    render(jsx);
    expect(screen.getAllByText("Review recommended").length).toBeGreaterThan(0);
  });

  it("links the passage-composition callout to the comparison's evidence page (Milestone 7A.4)", async () => {
    mockDetail = makeDetail();
    const jsx = await ComparisonPage({ params: Promise.resolve({ comparisonId: "cmp-1" }) });
    render(jsx);
    const link = screen.getByRole("link", { name: /explore passage evidence/i });
    expect(link).toHaveAttribute("href", "/comparisons/cmp-1/evidence");
  });

  it("renders technical details collapsed by default", async () => {
    mockDetail = makeDetail();
    const jsx = await ComparisonPage({ params: Promise.resolve({ comparisonId: "cmp-1" }) });
    render(jsx);
    const details = screen.getByText("Show technical details").closest("details");
    expect(details).not.toHaveAttribute("open");
  });

  it("calls notFound() for an unknown comparison id", async () => {
    mockDetail = null;
    await expect(ComparisonPage({ params: Promise.resolve({ comparisonId: "missing" }) })).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("renders a safe error state when the database is unavailable", async () => {
    mockShouldThrow = true;
    const jsx = await ComparisonPage({ params: Promise.resolve({ comparisonId: "cmp-1" }) });
    render(jsx);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    mockShouldThrow = false;
  });
});
