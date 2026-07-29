/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import type { ComparisonEvidenceFilterOptions, ComparisonEvidenceItem } from "@/lib/domain/passage";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

function makeDetail(): ReportComparisonDetail {
  return {
    id: "cmp-1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    gapMonths: 12,
    isTransition: false,
    isIrregularGap: false,
    isLatestForCompany: true,
    isHistoricalPeakChange: false,
    disclosureChangeScore: null,
    disclosureChangeLabel: null,
    disclosureChangePercentile: null,
    disclosureChangeQuality: null,
    disclosureChangeQualityLabel: null,
    disclosureChangePrimaryEligible: null,
    disclosureChangeWarning: null,
    netToneChange: null,
    netToneChangeLabel: null,
    uncertaintyChange: null,
    uncertaintyChangeLabel: null,
    riskIntroductionRate: null,
    riskIntroductionLabel: null,
    riskRemovalRate: null,
    riskRemovalLabel: null,
    governanceChange: null,
    governanceChangeLabel: null,
    financialConditionChange: null,
    financialConditionChangeLabel: null,
    reportSideQuality: "GOOD",
    reportSideQualityLabel: "Analysis ready",
    reportSidePrimaryEligible: true,
    alignmentChangeQuality: "USABLE",
    alignmentChangeQualityLabel: "Usable attribution",
    alignmentChangePrimaryEligible: true,
    primaryFindingKey: null,
    secondaryFindingKey: null,
    tertiaryFindingKey: null,
    findingPayload: null,
    dictionaryMatchRateEarlier: 0.9,
    dictionaryMatchRateLater: 0.9,
    ambiguousWordShare: 0.01,
    collisionFlaggedWordShare: 0.01,
    unmatchedWordShare: 0.01,
    structuredContentExclusionShare: 0.01,
    reportSideWarning: null,
    alignmentChangeWarning: null,
  };
}

function makeComposition(): PassageComposition {
  return {
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
    qualityNote: "note",
  };
}

const FILTER_OPTIONS: ComparisonEvidenceFilterOptions = { confidenceLevels: [], categories: [], subcategoriesByCategory: {} };

const EVIDENCE_ITEM: ComparisonEvidenceItem = {
  passageComparisonId: "pc1",
  alignmentStatus: "NEW",
  alignmentType: "UNMATCHED_LATER",
  confidence: "HIGH",
  confidenceLabel: "High confidence",
  collisionFlag: false,
  splitMergeFlag: false,
  contentScore: null,
  earlier: null,
  later: { passageId: "p1", heading: "New disclosure", excerpt: [{ text: "text", matched: false }], firstPageNumber: 1, lastPageNumber: 1, wordCount: 2 },
};

let mockDetail: ReportComparisonDetail | null = makeDetail();
let shouldThrow = false;

vi.mock("@/lib/repositories/postgres-comparison-repository", () => ({
  PostgresComparisonRepository: class {
    async getComparisonById() {
      if (shouldThrow) throw new Error("connection refused");
      return mockDetail;
    }
    async getComparisonPassageComposition() {
      if (shouldThrow) throw new Error("connection refused");
      return makeComposition();
    }
    async getComparisonEvidence() {
      return [EVIDENCE_ITEM];
    }
    async countComparisonEvidence() {
      return 1;
    }
    async getComparisonEvidenceFilterOptions() {
      return FILTER_OPTIONS;
    }
  },
}));

const { default: ComparisonEvidencePage } = await import("@/app/comparisons/[comparisonId]/evidence/page");

describe("/comparisons/[comparisonId]/evidence page", () => {
  it("renders header, summary counts, status tabs, and evidence rows", async () => {
    mockDetail = makeDetail();
    shouldThrow = false;
    const jsx = await ComparisonEvidencePage({
      params: Promise.resolve({ comparisonId: "cmp-1" }),
      searchParams: Promise.resolve({}),
    });
    render(jsx);
    expect(screen.getByText(/Acme Corp \(ACT\)/)).toBeInTheDocument();
    expect(screen.getByText("Total aligned passages")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^All/ })).toBeInTheDocument();
    expect(screen.getByText("New disclosure")).toBeInTheDocument();
  });

  it("calls notFound() for an unknown comparison id", async () => {
    mockDetail = null;
    await expect(
      ComparisonEvidencePage({ params: Promise.resolve({ comparisonId: "missing" }), searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("renders a safe error state when the database is unavailable", async () => {
    mockDetail = makeDetail();
    shouldThrow = true;
    const jsx = await ComparisonEvidencePage({
      params: Promise.resolve({ comparisonId: "cmp-1" }),
      searchParams: Promise.resolve({}),
    });
    render(jsx);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
    shouldThrow = false;
  });
});
